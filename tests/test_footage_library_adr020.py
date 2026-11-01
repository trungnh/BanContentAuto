"""
ADR-020 tests: local CLIP footage library, semantic window matching, one-call LLM choice,
YouTube block handling, no Tier-4 chain, duplicate detection, CLIP installer status.
All tests are offline (fake CLIP vectors, mocked yt-dlp / LLM).
"""

from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovideo.footage.clip_installer import CLIP_FILES, ClipInstaller, missing_model_files
from autovideo.footage.library import CatalogEntry, VideoIndex
from autovideo.footage.matcher import SceneFootageMatcher, SceneQuery
from autovideo.footage import scene_picker
from autovideo.production.semantic_judge import SemanticFootageJudge
from autovideo.sourcing.universal import (
    UniversalDownloader,
    UniversalDownloaderError,
    YouTubeBlockedError,
    _raise_if_blocked,
)

D = 8  # tiny embedding dim for tests


def _unit(i: int) -> np.ndarray:
    v = np.zeros(D, dtype=np.float32)
    v[i] = 1.0
    return v


class FakeClip:
    """Maps prompt text to fixed unit vectors: 'hyena'->axis0, 'bone'->axis1, 'nursing'->axis2, defects->axis7."""

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        out = []
        for t in texts:
            t = t.lower()
            v = np.zeros(D, dtype=np.float32)
            if "photo of a" in t:
                v[0] = 1.0
            elif any(k in t for k in ("talking", "captions", "game", "cartoon", "blurry", "player", "vehicle")):
                v[7] = 1.0
            else:
                if "bone" in t:
                    v[1] += 1.0
                if "nursing" in t:
                    v[2] += 1.0
                if not v.any():
                    v[3] = 1.0
            out.append(v / np.linalg.norm(v))
        return np.stack(out)


def _frames(spec: List[np.ndarray]) -> np.ndarray:
    e = np.stack(spec).astype(np.float32)
    return e / np.linalg.norm(e, axis=1, keepdims=True)


class FakeLib:
    def __init__(self, videos: Dict[str, VideoIndex]):
        self.videos = videos

    def flag_inauthentic(self, video_id: str) -> None:
        self.videos[video_id].entry.inauthentic = True


def _video(vid: str, frames: List[np.ndarray], title: str = "spotted hyena clip", cuts=None) -> VideoIndex:
    entry = CatalogEntry(video_id=vid, path=Path(f"C:/raw/{vid}.mp4"), title=title)
    times = np.arange(len(frames), dtype=np.float32) + 0.5
    return VideoIndex(entry, times, _frames(frames), list(cuts or []), float(len(frames)))


HYENA = _unit(0)
BONE_HYENA = (_unit(0) + _unit(1))
NURSE_HYENA = (_unit(0) + _unit(2))
NO_HYENA = _unit(3)


@pytest.fixture
def lib():
    # video A: 0-10s hyena walking, 10-20s hyena chewing bone ; video B: nursing ; video C: no hyena (lion)
    a = _video("A", [HYENA] * 10 + [BONE_HYENA] * 10)
    b = _video("B", [NURSE_HYENA] * 15)
    c = _video("C", [NO_HYENA] * 20, title="lion pride spotted hyena")
    return FakeLib({"A": a, "B": b, "C": c})


def _matcher(lib, **kw):
    return SceneFootageMatcher(lib, FakeClip(), "spotted hyena", subject_min=kw.pop("subject_min", 0.5), **kw)


def test_matcher_finds_semantic_window_inside_video(lib):
    m = _matcher(lib)
    c = m.candidates(SceneQuery("S1", 6.0, ["spotted hyena crushing bone close up"]), {}, {}, top_k=3)
    assert c[0].video_id == "A"
    assert c[0].start >= 9.5 and c[0].end <= 20.0  # cut lands in the bone-chewing part, not 0-10s


def test_matcher_rejects_windows_without_subject(lib):
    m = _matcher(lib)
    c = m.candidates(SceneQuery("S1", 5.0, ["savanna landscape"]), {}, {}, top_k=5)
    assert all(x.video_id != "C" for x in c)  # video C never shows a hyena (subject score 0)


def test_matcher_respects_used_windows_and_reuse_cap(lib):
    m = _matcher(lib, max_reuse_per_video=2)
    q = SceneQuery("S1", 6.0, ["hyena chewing bone"])
    first = m.candidates(q, {}, {}, top_k=1)[0]
    used = {"A": [(first.start, first.end)]}
    second = m.candidates(q, used, {"A": 1}, top_k=1)[0]
    assert second.video_id != "A" or second.end <= first.start or second.start >= first.end
    capped = m.candidates(q, used, {"A": 2}, top_k=5)
    assert all(x.video_id != "A" for x in capped)


def test_matcher_never_exceeds_source_duration(lib):
    m = _matcher(lib)
    c = m.candidates(SceneQuery("S1", 18.0, ["hyena nursing cubs"]), {}, {}, top_k=5)
    for x in c:
        assert x.end <= lib.videos[x.video_id].duration_sec + 1e-6
    assert all(x.video_id != "B" for x in c)  # B is only 15s long


def test_confidence_gate():
    from autovideo.footage.matcher import WindowCandidate as W
    strong = [W("A", 0, 5, .4, .3, .1, .40), W("B", 0, 5, .3, .3, .1, .30)]
    close = [W("A", 0, 5, .4, .3, .1, .40), W("B", 0, 5, .39, .3, .1, .39)]
    assert SceneFootageMatcher.is_confident(strong)
    assert not SceneFootageMatcher.is_confident(close)


# ------------------------------------------------------------------ scene picker
def _patch_qa_clean():
    res = MagicMock(is_clean=True, defects=[])
    return patch.object(scene_picker.VisualQualityInspector, "inspect_video_segment", return_value=res)


def test_picker_uses_one_llm_call_and_returns_choice(lib):
    m = _matcher(lib)
    judge = MagicMock(spec=SemanticFootageJudge)
    judge.choose_best.return_value = {"verdict": "pass", "index": 0, "score": 8.0, "scores": {"A": 8}, "reason": "ok"}
    with _patch_qa_clean(), patch.object(SceneFootageMatcher, "is_confident", return_value=False):
        acc, fb = scene_picker.pick_library_window(
            lib=lib, matcher=m, judge=judge, scene_id="S1", duration=6.0, narration="n",
            visual_prompt="spotted hyena crushing bone", en_keywords=[], subject_anchor="spotted hyena",
            used_intervals={}, used_counts={}, ffmpeg_bin=None)
    assert judge.choose_best.call_count == 1
    assert acc is not None and fb is None
    assert acc["semantic"]["method"] == "llm_choose_best"
    assert acc["sourced"].vault_source == "library" and acc["sourced"].metadata["video_id"] == "A"


def test_picker_skips_llm_when_clip_confident(lib):
    m = _matcher(lib)
    judge = MagicMock(spec=SemanticFootageJudge)
    with _patch_qa_clean(), patch.object(SceneFootageMatcher, "is_confident", return_value=True):
        acc, _ = scene_picker.pick_library_window(
            lib=lib, matcher=m, judge=judge, scene_id="S1", duration=6.0, narration="n",
            visual_prompt="spotted hyena crushing bone", en_keywords=[], subject_anchor="spotted hyena",
            used_intervals={}, used_counts={}, ffmpeg_bin=None)
    judge.choose_best.assert_not_called()
    assert acc["semantic"]["verdict"] == "clip_confident"


def test_picker_below_threshold_becomes_fallback(lib):
    m = _matcher(lib)
    judge = MagicMock(spec=SemanticFootageJudge)
    judge.choose_best.return_value = {"verdict": "fail", "index": 1, "score": 4.0, "scores": {"A": 3, "B": 4}}
    with _patch_qa_clean(), patch.object(SceneFootageMatcher, "is_confident", return_value=False):
        acc, fb = scene_picker.pick_library_window(
            lib=lib, matcher=m, judge=judge, scene_id="S1", duration=6.0, narration="n",
            visual_prompt="hyena", en_keywords=["hyena nursing cubs"], subject_anchor="spotted hyena",
            used_intervals={}, used_counts={}, ffmpeg_bin=None)
    assert acc is None and fb is not None


# ------------------------------------------------------------------ judge choose_best
def test_ai_generated_video_is_excluded_afterwards(lib):
    m = _matcher(lib)
    judge = MagicMock(spec=SemanticFootageJudge)
    judge.choose_best.return_value = {"verdict": "pass", "index": 1, "score": 7.0, "ai_generated_indices": [0]}
    q_kwargs = dict(narration="n", visual_prompt="spotted hyena crushing bone", en_keywords=[],
                    subject_anchor="spotted hyena", used_intervals={}, used_counts={}, ffmpeg_bin=None)
    with _patch_qa_clean(), patch.object(SceneFootageMatcher, "is_confident", return_value=False):
        first = m.candidates(SceneQuery("S1", 6.0, ["spotted hyena crushing bone"]), {}, {}, top_k=1)[0].video_id
        scene_picker.pick_library_window(lib=lib, matcher=m, judge=judge, scene_id="S1", duration=6.0, **q_kwargs)
    assert lib.videos[first].entry.inauthentic is True
    assert all(v.entry.video_id != first for v in m.eligible_videos())


def test_choose_best_ai_rows_are_unusable():
    j = _judge()
    raw = '{"scores": {"A": 9, "B": 6}, "unusable": [], "ai_generated": ["A"], "best": "A"}'
    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", return_value=raw):
        r = j.choose_best([{"path": "x", "start": 0, "duration": 5}] * 2, "n", "p", "spotted hyena")
    assert r["index"] == 1 and r["ai_generated_indices"] == [0]


# ------------------------------------------------------------------ judge choose_best (parsing)
def _judge():
    return SemanticFootageJudge(enabled=True, api_key="k", model="m", min_score=5)


def test_choose_best_parses_and_skips_unusable():
    j = _judge()
    raw = '{"scores": {"A": 9, "B": 7}, "unusable": ["A"], "best": "A", "reason": "A has captions"}'
    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", return_value=raw) as call:
        r = j.choose_best([{"path": "x", "start": 0, "duration": 5}] * 2, "n", "p", "spotted hyena")
    assert call.call_count == 1
    assert r["index"] == 1 and r["verdict"] == "pass" and r["score"] == 7


def test_choose_best_none_usable_fails():
    j = _judge()
    raw = '{"scores": {"A": 2}, "unusable": ["A"], "best": "none"}'
    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", return_value=raw):
        r = j.choose_best([{"path": "x", "start": 0, "duration": 5}], "n", "p", "spotted hyena")
    assert r["index"] is None and r["verdict"] == "fail"


# ------------------------------------------------------------------ YouTube handling
def test_block_markers_raise_specific_error():
    with pytest.raises(YouTubeBlockedError):
        _raise_if_blocked(RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot"))
    _raise_if_blocked(RuntimeError("some other error"))  # no raise


def test_search_uses_flat_listing():
    dl = UniversalDownloader()
    with patch("autovideo.sourcing.universal.yt_dlp.YoutubeDL") as Y:
        Y.return_value.__enter__.return_value.extract_info.return_value = {"entries": []}
        dl.get_video_info("ytsearch8:spotted hyena")
        opts = Y.call_args[0][0]
    assert opts.get("extract_flat") == "in_playlist"


def test_download_stops_immediately_when_blocked(tmp_path):
    dl = UniversalDownloader()
    entries = [{"id": f"v{i}", "title": f"spotted hyena bone {i}", "duration": 60} for i in range(5)]
    with patch.object(dl, "get_video_info", return_value={"entries": entries}), \
         patch.object(dl, "_download_and_verify", side_effect=YouTubeBlockedError("blocked")) as mock_dl:
        with pytest.raises(YouTubeBlockedError):
            dl.download("ytsearch8:spotted hyena bone", output_dir=tmp_path, subject_anchor="spotted hyena")
    assert mock_dl.call_count == 1


def test_download_tries_at_most_three(tmp_path):
    dl = UniversalDownloader()
    entries = [{"id": f"v{i}", "title": f"spotted hyena bone {i}", "duration": 60} for i in range(6)]
    with patch.object(dl, "get_video_info", return_value={"entries": entries}), \
         patch.object(dl, "_download_and_verify", side_effect=RuntimeError("fail")) as mock_dl:
        with pytest.raises(UniversalDownloaderError):
            dl.download("ytsearch8:spotted hyena bone", output_dir=tmp_path, subject_anchor="spotted hyena")
    assert mock_dl.call_count == 3


def test_cached_download_is_reused(tmp_path):
    dl = UniversalDownloader()
    cached = tmp_path / "universal_abc.mp4"
    cached.write_bytes(b"x" * 20000)
    with patch.object(dl, "_verify_video_file", return_value=True), \
         patch("autovideo.sourcing.universal.yt_dlp.YoutubeDL") as Y:
        p = dl._download_and_verify("https://youtube.com/watch?v=abc", "abc", tmp_path)
    assert p == cached
    Y.assert_not_called()


# ------------------------------------------------------------------ coordinator
def test_tier4_chain_removed_from_pipeline():
    import inspect
    import autovideo.coordinator as coord
    src = inspect.getsource(coord.MasterPipelineCoordinator._run_pipeline_body)
    assert "tier4_reused_footage" not in src
    assert "for rec in reversed(retained_completed_scenes)" not in src
    assert "pick_library_window" in src and "YouTubeBlockedError" in src


def test_duplicate_detection_flags_identical_frames(tmp_path):
    from autovideo.coordinator import MasterPipelineCoordinator
    rng = np.random.default_rng(0)
    img_a = (rng.random((90, 160, 3)) * 255).astype(np.uint8)
    img_b = (rng.random((90, 160, 3)) * 255).astype(np.uint8)
    recs = []
    for sid in ("S1", "S2", "S3"):
        p = tmp_path / f"{sid}.mp4"
        p.write_bytes(b"0" * 4096)
        recs.append(MagicMock(scene_id=sid, video_path=str(p), duration_sec=5.0))
    frames = {"S1": img_a, "S2": img_b, "S3": img_a.copy()}
    coord = MasterPipelineCoordinator.__new__(MasterPipelineCoordinator)
    coord.config = MagicMock()
    with patch("autovideo.coordinator.BinaryManager") as BM, \
         patch("autovideo.coordinator.VisualQualityInspector._extract_frame",
               side_effect=lambda p, t, ffmpeg_bin=None: frames[Path(p).stem]):
        BM.return_value.find_binary.return_value = (None, None)
        dups = coord._detect_duplicate_scenes(recs)
    assert ("S1", "S3", 0) in dups
    assert all(not (a == "S1" and b == "S2") for a, b, _ in dups)


# ------------------------------------------------------------------ installer
def test_clip_installer_reports_missing_files(tmp_path):
    assert set(missing_model_files(tmp_path)) == set(CLIP_FILES)
    for name in CLIP_FILES:
        (tmp_path / name).write_bytes(b"x")
    assert missing_model_files(tmp_path) == []


def test_clip_installer_status_shape(tmp_path):
    inst = ClipInstaller.__new__(ClipInstaller)
    inst.model_dir = tmp_path
    st = inst.status()
    for key in ("installed", "is_available", "missing_packages", "missing_files", "install_state", "progress"):
        assert key in st
    assert st["installed"] is False
