"""
ADR-019 regression tests: footage must match the scene, not just mention the subject.

Fixtures are the REAL off-topic videos selected in proj_f2668146 (SCENE_006/009/026/028/030/037).
Unlike the retired inline-copy test, these tests exercise the production code paths.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autovideo.coordinator import MasterPipelineCoordinator
from autovideo.production.semantic_judge import (
    SemanticFootageJudge,
    SemanticJudgeResult,
    parse_judge_response,
)
from autovideo.sourcing.engine import AssetSourcingEngine
from autovideo.sourcing.relevance import (
    anchor_head,
    anchor_matches,
    extract_scene_terms,
    matched_scene_terms,
)
from autovideo.sourcing.universal import UniversalDownloader, UniversalDownloaderError

ANCHOR = "spotted hyena"


def _entry(vid, title, desc="", uploader="Someone", duration=60.0):
    return {"id": vid, "title": title, "description": desc, "uploader": uploader,
            "duration": duration, "height": 1080, "width": 1920}


# Real wrong picks from proj_f2668146 (title + description excerpt)
OFF_TOPIC = {
    "SCENE_028": _entry("fNoa_DYrO2A", "Crimson Desert How to Fix Bugged Quests (Bug Fix Tips and Tricks)",
                        "Crimson Desert is a HUGE game with a massive map"),
    "SCENE_030": _entry("WikLFmUgecs", "MRI for brain conditions",
                        "Magnetic resonance imaging (MRI) of the brain/head is a painless test"),
    "SCENE_037": _entry("tykiIT95SSI", "EASY VIDEO LIGHTING in 2 Minutes.",
                        "How to instantly make your videos looking better and more professional."),
    "SCENE_026": _entry("EfklYBxBNyQ", "R5, Lepiyayoi mating Bella daughter Noletira, smooth gentle boy, MaasaiMara lions",
                        "R5, Lepiyayoi today, mating Bella's daughter Noletira."),
}

SCENE_KEYWORDS = {
    "SCENE_028": (["wildlife biology field research station screens", "hyena research camp night computer gps"],
                  "Wide interior of a wildlife research station tent at night; biologist monitoring thermal computer screens tracking hyena clan movements on maps."),
    "SCENE_030": (["mri brain scan hyena skull monitor", "3d cranial brain rendering hyena frontal lobe"],
                  "Closeup of a glowing blue 3D MRI brain scan rotation of a spotted hyena skull on a laboratory monitor."),
    "SCENE_037": (["majestic spotted hyena on termite mound portrait", "hyena looking directly into camera cinematic lighting"],
                  "Cinematic medium portrait shot of a majestic spotted hyena standing tall on a termite mound."),
    "SCENE_026": (["spotted hyena eye macro lantern reflection", "hyena amber eye extreme close up"],
                  "Detail macro shot of a spotted hyena's amber eye reflecting the lantern light."),
    "SCENE_006": (["spotted hyena premolar teeth enamel macro", "bone crushing teeth structure carnassial"],
                  "Extreme macro rack focus on the massive conical premolar teeth of a hyena skull."),
}


# ---------------------------------------------------------------- relevance rules
def test_anchor_rules_are_shared_and_head_noun_based():
    assert anchor_head(ANCHOR) == "hyena"
    assert anchor_matches("Hyena chasing wildebeest", ANCHOR)
    assert anchor_matches("Spotted Hyenas at waterhole", ANCHOR)
    # Modifier-only match must NOT count (old bug class: 'spotted' deer)
    assert not anchor_matches("Spotted deer grazing in India", ANCHOR)
    assert not anchor_matches("MRI for brain conditions", ANCHOR)


def test_build_natural_query_uses_same_anchor_rule():
    build = MasterPipelineCoordinator._build_natural_query
    assert build("hyena pack tactical hunt savanna", ANCHOR) == "hyena pack tactical hunt savanna"
    assert build("wildlife biology field research station", ANCHOR) == "spotted hyena wildlife biology field research station"
    assert build("spotted deer running", ANCHOR) == "spotted hyena spotted deer running"


def test_scene_terms_exclude_anchor_and_generic_words():
    kws, vp = SCENE_KEYWORDS["SCENE_006"]
    terms = extract_scene_terms(kws, vp, ANCHOR)
    assert "premolar" in terms and "teeth" in terms
    assert "hyena" not in terms and "spotted" not in terms and "macro" not in terms
    assert matched_scene_terms("Hyena Cub Gets Stuck in a Well in Turkey", terms) == []


# ---------------------------------------------------------------- universal scoring
@pytest.mark.parametrize("scene_id", sorted(OFF_TOPIC))
def test_real_off_topic_picks_are_rejected(scene_id, tmp_path: Path):
    """Every off-topic video actually chosen in proj_f2668146 must now be rejected."""
    kws, vp = SCENE_KEYWORDS[scene_id]
    terms = extract_scene_terms(kws, vp, ANCHOR)
    dl = UniversalDownloader()
    with patch.object(dl, "get_video_info", return_value={"entries": [OFF_TOPIC[scene_id]]}), \
         patch.object(dl, "_download_and_verify", return_value=tmp_path / "x.mp4"):
        with pytest.raises(UniversalDownloaderError):
            dl.download(f"ytsearch8:{kws[1]}", output_dir=tmp_path, subject_anchor=ANCHOR, scene_terms=terms)


def test_subject_only_match_without_scene_terms_is_rejected(tmp_path: Path):
    """SCENE_006: title mentions 'Hyena' but nothing about teeth -> rejected by scene-term gate."""
    kws, vp = SCENE_KEYWORDS["SCENE_006"]
    terms = extract_scene_terms(kws, vp, ANCHOR)
    entries = [
        _entry("Ml5OwD_qpWE", "Hyena Cub Gets Stuck in a Well in Turkey",
               "A hyena cub that slipped down a well in Turkey got a lucky break."),
        _entry("good_teeth", "Spotted hyena teeth crushing bone close up", "Massive premolar teeth in action"),
    ]
    dl = UniversalDownloader()
    with patch.object(dl, "get_video_info", return_value={"entries": entries}), \
         patch.object(dl, "_download_and_verify", return_value=tmp_path / "good.mp4") as mock_dl:
        res = dl.download("ytsearch8:spotted hyena premolar teeth", output_dir=tmp_path,
                          subject_anchor=ANCHOR, scene_terms=terms)
    assert res.video_id == "good_teeth"
    assert mock_dl.call_args[0][1] == "good_teeth"


def test_reuse_cap_excludes_video_ids(tmp_path: Path):
    entries = [
        _entry("zYDTBt6ms48", "Spotted Hyenas - strange behaviour at waterhole", "hyena family at a water hole"),
        _entry("other", "Spotted hyena drinking at waterhole", "hyena water hole"),
    ]
    dl = UniversalDownloader()
    with patch.object(dl, "get_video_info", return_value={"entries": entries}), \
         patch.object(dl, "_download_and_verify", return_value=tmp_path / "o.mp4"):
        res = dl.download("ytsearch8:spotted hyena waterhole", output_dir=tmp_path, subject_anchor=ANCHOR,
                          scene_terms=["waterhole", "water"], exclude_video_ids=["zYDTBt6ms48"])
    assert res.video_id == "other"


def test_engine_forwards_scene_terms_and_exclusions(tmp_path: Path):
    engine = AssetSourcingEngine()
    fake = MagicMock(downloaded_path=tmp_path / "a.mp4", duration_sec=30.0, width=1920, height=1080,
                     extractor="youtube", video_id="v1", title="t", webpage_url="", uploader="",
                     chapters=None, categories=None, description="")
    with patch.object(engine.universal, "download", return_value=fake) as mock_dl:
        engine.source_scene_asset(scene_id="SCENE_001", query="hyena pack hunt", preferred_vault="universal",
                                  subject_anchor=ANCHOR, scene_terms=["hunt"], exclude_video_ids=["x"])
    kwargs = mock_dl.call_args[1]
    assert kwargs["subject_anchor"] == ANCHOR
    assert kwargs["scene_terms"] == ["hunt"]
    assert kwargs["exclude_video_ids"] == ["x"]
    assert '"spotted hyena"' in mock_dl.call_args[0][0]


# ---------------------------------------------------------------- coordinator helpers
def test_resolve_segment_offset_rejects_short_source_and_avoids_overlap():
    resolve = MasterPipelineCoordinator._resolve_segment_offset
    # SCENE_013 class: 4s source for a 7.5s scene -> would be padded with black
    assert resolve(1.0, 7.5, 4.0, []) is None
    # Offset clamped so the window stays inside the source
    assert resolve(50.0, 8.0, 40.0, []) == pytest.approx(32.0)
    # 022/024/036 class: same 0:38 window must not be reused
    off = resolve(38.0, 8.0, 80.0, [(38.0, 46.0)])
    assert off is not None and (off >= 46.0 or off + 8.0 <= 38.0)
    # Exactly-as-long source is fine
    assert resolve(0.0, 5.0, 5.0, []) == 0.0


def test_track_footage_usage_counts_videos_and_intervals():
    counts, intervals = {}, {}
    meta = {"video_id": "v1", "raw_asset_path": "C:/raw/v1.mp4", "start_offset_sec": 10.0, "duration_sec": 7.0}
    MasterPipelineCoordinator._track_footage_usage(meta, counts, intervals)
    MasterPipelineCoordinator._track_footage_usage(meta, counts, intervals)
    assert counts["v1"] == 2
    assert (10.0, 17.0) in intervals["C:/raw/v1.mp4"]


def test_coordinator_always_passes_subject_anchor_source():
    """Guard against re-introducing the conditional anchor bypass (RC-1)."""
    import inspect
    import autovideo.coordinator as coord_mod
    src = inspect.getsource(coord_mod.MasterPipelineCoordinator._run_pipeline_body)
    assert "pass_anchor" not in src and "primary_anchor" not in src
    # Every online sourcing call must carry the anchor (ADR-020 removed the relaxed-duration retry call)
    n_calls = src.count("self.sourcing_engine.source_scene_asset(")
    assert n_calls >= 1
    assert src.count("subject_anchor=subject_anchor,") >= n_calls
    assert "scene_terms=scene_terms" in src


# ---------------------------------------------------------------- semantic judge
def test_judge_parse_tolerates_code_fences_and_comments():
    raw = '```json\n{"subject_present": true, // yes\n "is_real_footage": true, "overlay_text_or_watermark": false, "match_score": 7, "reason": "ok"}\n```'
    data = parse_judge_response(raw)
    assert data["match_score"] == 7 and data["subject_present"] is True


def _judge_with_response(payload: dict, tmp_path: Path, **kw) -> SemanticJudgeResult:
    import json as _json
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 4096)
    j = SemanticFootageJudge(enabled=True, api_key="k", model="m", min_score=6, **kw)
    with patch.object(j, "_sample_frames", return_value=(["a", "b", "c"], [0.0, 1.0, 2.0])), \
         patch.object(j, "_call_ninerouter", return_value=_json.dumps(payload)):
        return j.judge(video, 0.0, 5.0, "narration", "prompt", ANCHOR)


def test_judge_rejects_game_footage(tmp_path: Path):
    r = _judge_with_response({"subject_present": False, "is_real_footage": False,
                              "overlay_text_or_watermark": True, "match_score": 0, "reason": "video game"}, tmp_path)
    assert r.verdict == "fail"


def test_judge_passes_good_match_and_rejects_overlay(tmp_path: Path):
    good = {"subject_present": True, "is_real_footage": True, "overlay_text_or_watermark": False, "match_score": 8}
    assert _judge_with_response(good, tmp_path).verdict == "pass"
    assert _judge_with_response({**good, "overlay_text_or_watermark": True}, tmp_path).verdict == "fail"
    assert _judge_with_response({**good, "overlay_text_or_watermark": True}, tmp_path,
                                reject_overlays=False).verdict == "pass"
    assert _judge_with_response({**good, "match_score": 4}, tmp_path).verdict == "fail"


def test_judge_circuit_breaker_reports_unavailable(tmp_path: Path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 4096)
    j = SemanticFootageJudge(enabled=True, api_key="k", model="m")
    with patch.object(j, "_sample_frames", return_value=(["a", "b"], [0.0, 1.0])), \
         patch.object(j, "_call_ninerouter", side_effect=RuntimeError("down")):
        results = [j.judge(video, 0.0, 5.0, "n", "p", ANCHOR) for _ in range(4)]
    assert all(r.verdict == "unavailable" for r in results)
    assert not j.active  # circuit open after 3 consecutive errors


def test_judge_inactive_without_api_key():
    assert not SemanticFootageJudge(enabled=True, api_key="", model="m").active
