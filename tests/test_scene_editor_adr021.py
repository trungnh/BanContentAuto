"""
ADR-021 tests: global shot planner, diversity, crop-detection guard, blur gate, confusers,
footage-aware rewrite, and the dashboard Scene Editor (redo / alternatives / apply / rerender).
Offline: fake CLIP vectors, mocked ffmpeg / LLM / muxer.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovideo.footage.matcher import SceneFootageMatcher, SceneQuery, WindowCandidate as W
from autovideo.production.semantic_judge import SemanticFootageJudge
from autovideo.production.visual_inspector import VisualQualityInspector

from tests.test_footage_library_adr020 import FakeClip, FakeLib, _video, HYENA, BONE_HYENA, NURSE_HYENA  # noqa: E402


# ------------------------------------------------------------------ planner (B1)
def test_regret_planner_gives_scarce_footage_to_the_scene_that_needs_it():
    lib = FakeLib({"A": _video("A", [HYENA] * 20), "B": _video("B", [NURSE_HYENA] * 20), "C": _video("C", [HYENA] * 20)})
    m = SceneFootageMatcher(lib, FakeClip(), "spotted hyena", subject_min=0.5, max_reuse_per_video=1)
    pools = {
        "S1": [W("B", 0, 6, .40, .5, 0, .40), W("A", 0, 6, .39, .5, 0, .39)],   # S1 is happy with A too
        "S2": [W("B", 0, 6, .40, .5, 0, .40), W("C", 0, 6, .20, .5, 0, .20)],   # S2 really needs B
    }
    with patch.object(m, "top_windows", side_effect=lambda q, *a, **k: pools[q.scene_id]), \
         patch.object(m, "window_embedding", return_value=None):
        plan = m.plan([SceneQuery("S1", 6, ["x"]), SceneQuery("S2", 6, ["y"])], {}, {})
    assert plan["S2"][0].video_id == "B"
    assert plan["S1"][0].video_id == "A"   # sequential greedy would have given S1 'B' and S2 a 0.20 shot


def test_planner_never_assigns_overlapping_windows():
    lib = FakeLib({"A": _video("A", [BONE_HYENA] * 30)})
    m = SceneFootageMatcher(lib, FakeClip(), "spotted hyena", subject_min=0.5, max_reuse_per_video=3)
    qs = [SceneQuery(f"S{i}", 6.0, ["hyena chewing bone"]) for i in range(3)]
    plan = m.plan(qs, {}, {}, per_video=3)
    wins = [plan[q.scene_id][0] for q in qs if plan[q.scene_id]]
    for i in range(len(wins)):
        for j in range(i):
            assert wins[i].end <= wins[j].start or wins[i].start >= wins[j].end


def test_diversity_penalty_only_for_near_duplicates():
    lib = FakeLib({"A": _video("A", [HYENA] * 10)})
    m = SceneFootageMatcher(lib, FakeClip(), "spotted hyena", diversity_threshold=0.92, diversity_weight=0.5)
    e = np.zeros(8, np.float32); e[0] = 1
    far = np.zeros(8, np.float32); far[3] = 1
    assert m.diversity_penalty(e, np.stack([e])) == pytest.approx(0.04)
    assert m.diversity_penalty(e, np.stack([far])) == 0.0
    assert m.diversity_penalty(e, None) == 0.0


def test_confuser_penalty_demotes_lookalike_species():
    jackal = np.zeros(8, np.float32); jackal[0] = 0.6; jackal[5] = 1.0  # weak 'hyena' + strong 'jackal' axis
    lib = FakeLib({"J": _video("J", [jackal] * 10), "H": _video("H", [HYENA] * 10)})

    class ConfClip(FakeClip):
        def embed_texts(self, texts):
            out = []
            for t in texts:
                if "jackal" in t.lower():
                    v = np.zeros(8, np.float32); v[5] = 1.0; out.append(v)
                else:
                    out.append(super().embed_texts([t])[0])
            return np.stack(out)

    m = SceneFootageMatcher(lib, ConfClip(), "spotted hyena", subject_min=0.4)
    before = {c.video_id: c.total for c in m.candidates(SceneQuery("S", 5, ["savanna"]), {}, {}, top_k=5)}
    m.set_confusers(["black-backed jackal"])
    after = {c.video_id: c.total for c in m.candidates(SceneQuery("S", 5, ["savanna"]), {}, {}, top_k=5)}
    assert after["J"] < before["J"]
    assert after["H"] == pytest.approx(before["H"])


# ------------------------------------------------------------------ crop guard (bug found in review)
def test_videos_about_confuser_species_are_not_eligible():
    lib = FakeLib({
        "S": _video("S", [HYENA] * 10, title="Striped Hyena walking"),
        "M": _video("M", [HYENA] * 10, title="Wild Dog and Spotted Hyena Interaction"),
        "H": _video("H", [HYENA] * 10, title="Hyena running"),
    })
    m = SceneFootageMatcher(lib, FakeClip(), "spotted hyena")
    m.set_confusers(["striped hyena", "African wild dog"])
    ids = {v.entry.video_id for v in m.eligible_videos()}
    assert ids == {"M", "H"}


def _fake_cropdetect(crop: str):
    proc = MagicMock(stderr=f"[Parsed_cropdetect_0] crop={crop}\n" * 25)
    return proc


@pytest.mark.parametrize("crop,expected", [
    ("384:1008:6:8", None),                       # 19% of the frame -> was a 5x zoom into a corner
    ("1920:864:0:108", "crop=1920:864:0:108"),    # genuine letterbox
    ("1440:1080:240:0", "crop=1440:1080:240:0"),  # genuine pillarbox
])
def test_detect_crop_region_rejects_non_letterbox_crops(tmp_path, crop, expected):
    from autovideo.production import transformer
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 2048)
    bm = MagicMock()
    bm.check_binary.return_value = SimpleNamespace(is_available=True, path="ffmpeg")
    with patch.object(transformer.subprocess, "run", return_value=_fake_cropdetect(crop)) as run, \
         patch.object(transformer, "probe_video", return_value=SimpleNamespace(width=1920, height=1080)):
        assert transformer.detect_crop_region(f, binary_manager=bm, start_sec=33.0) == expected
    assert "-ss" in run.call_args[0][0]  # samples the actual cut window, not the intro


# ------------------------------------------------------------------ blur gate
def test_blurry_segment_is_rejected(tmp_path):
    rng = np.random.default_rng(1)
    sharp = (rng.random((360, 640, 3)) * 255).astype(np.uint8)
    blurry = cv2_blur(sharp)
    assert VisualQualityInspector.laplacian_sharpness(sharp) > 500
    assert VisualQualityInspector.laplacian_sharpness(blurry) < VisualQualityInspector.BLUR_THRESHOLD
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 4096)
    with patch.object(VisualQualityInspector, "_extract_frame", return_value=blurry):
        res = VisualQualityInspector.inspect_video_segment(f, 0.0, 5.0)
    assert not res.is_clean and any(d.startswith("blurry") for d in res.defects)


def cv2_blur(img):
    import cv2
    return cv2.GaussianBlur(img, (0, 0), 12)


# ------------------------------------------------------------------ judge text calls (B3/B4)
def _judge():
    return SemanticFootageJudge(enabled=True, api_key="k", model="m", min_score=5)


def test_suggest_confusers_parses_and_drops_anchor():
    j = _judge()
    with patch.object(j, "_call_ninerouter", return_value='{"confusers": ["black-backed jackal", "spotted hyena", "African wild dog"]}'):
        assert j.suggest_confusers("spotted hyena") == ["black-backed jackal", "African wild dog"]


def test_rewrite_visual_prompts_parses_batch():
    j = _judge()
    raw = '{"scenes": {"SCENE_031": {"visual_prompt": "spotted hyena sniffing dry ground", "keywords": ["hyena sniffing", "hyena dung"]}}}'
    with patch.object(j, "_call_ninerouter", return_value=raw) as call:
        out = j.rewrite_visual_prompts([{"scene_id": "SCENE_031", "narration": "n", "visual_prompt": "white droppings beetle"}],
                                       ["Hyena mom and her cubs"], "spotted hyena")
    assert call.call_count == 1
    assert out["SCENE_031"]["visual_prompt"].startswith("spotted hyena")


def test_choose_best_prompt_contains_species_check():
    j = _judge()
    captured = {}

    def fake_call(prompt, images):
        captured["prompt"] = prompt
        return '{"scores": {"A": 7}, "unusable": [], "best": "A"}'

    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", side_effect=fake_call):
        j.choose_best([{"path": "x", "start": 0, "duration": 5}], "n", "p", "spotted hyena",
                      confusers=["black-backed jackal"])
    assert "black-backed jackal" in captured["prompt"] and "SPECIES CHECK" in captured["prompt"]


# ------------------------------------------------------------------ Scene editor (part A)
def _editor(tmp_path, running=False, flagged=("S2",)):
    from autovideo.scene_editor import SceneEditor
    recs = []
    for i, sid in enumerate(("S1", "S2", "S3"), start=1):
        p = tmp_path / f"scene_{i:03d}.mp4"
        p.write_bytes(b"0" * 4096)
        recs.append(SimpleNamespace(
            scene_id=sid, text=f"t{i}", duration_sec=5.0, video_path=str(p), audio_path=str(tmp_path / "a.wav"),
            source_info={}, metadata={"video_id": "A", "start_offset_sec": (i - 1) * 6.0, "duration_sec": 5.0,
                                      "raw_asset_path": str(tmp_path / "A.mp4"), "needs_review": sid in flagged},
        ))
    stage = SimpleNamespace(value="B2_SOURCING_TTS" if running else "COMPLETE")
    project = SimpleNamespace(project_id="p1", stage=stage, progress=100.0, completed_scenes=recs,
                              topic="Linh cẩu", skill_id="nature-wildlife-survival", screenplay={}, final_video_path="")
    coord = MagicMock()
    coord.projects = {"p1": project}
    coord._running_project_id = "p1" if running else None
    coord.config.paths.cache_temp_scenes_dir = tmp_path / "temp"
    coord.config.paths.cache_dir = tmp_path / "cache"
    coord.config.paths.get_project_render_dir.return_value = tmp_path / "render"
    from autovideo.coordinator import MasterPipelineCoordinator
    coord._track_footage_usage.side_effect = MasterPipelineCoordinator._track_footage_usage
    return SceneEditor(coord), coord, project


def test_editor_refuses_while_pipeline_running(tmp_path):
    from autovideo.scene_editor import SceneEditError
    ed, _, _ = _editor(tmp_path, running=True)
    with pytest.raises(SceneEditError):
        ed.redo_scene("p1", "S1")


def test_editor_redo_flagged_requires_flags(tmp_path):
    from autovideo.scene_editor import SceneEditError
    ed, _, _ = _editor(tmp_path, flagged=())
    with pytest.raises(SceneEditError):
        ed.redo_flagged("p1")


def test_used_by_others_excludes_the_edited_scene(tmp_path):
    ed, _, project = _editor(tmp_path)
    iv, ct = ed._used_by_others(project, "S2")
    assert ct["A"] == 2
    assert (6.0, 11.0) not in iv["A"] and (0.0, 5.0) in iv["A"] and (12.0, 17.0) in iv["A"]


def test_recut_updates_record_and_saves(tmp_path):
    ed, coord, project = _editor(tmp_path)
    vid_path = tmp_path / "B.mp4"
    vid_path.write_bytes(b"0" * 4096)
    entry = SimpleNamespace(video_id="B", path=vid_path, title="Hyena mom and her cubs", description="", uploader="u",
                            webpage_url="https://www.youtube.com/watch?v=B", inauthentic=False)
    lib = SimpleNamespace(videos={"B": SimpleNamespace(entry=entry, duration_sec=60.0)})
    sc = SimpleNamespace(scene_id="S2", visual_prompt="nursing", keywords=SimpleNamespace(en=["hyena nursing"]))
    out_tmp = tmp_path / "temp" / "p1" / "scene_002.edit.mp4"

    def fake_mux(**kw):
        Path(kw["output_path"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kw["output_path"]).write_bytes(b"1" * 4096)
        return SimpleNamespace(output_path=Path(kw["output_path"]), duration_sec=5.0)

    coord.scene_muxer.assemble_scene.side_effect = fake_mux
    with patch.object(ed, "_scene_ctx", return_value=(2, sc, project.completed_scenes[1])), \
         patch.object(ed, "_library", return_value=(lib, MagicMock(), MagicMock())):
        ed._recut(project, "S2", "B", 12.0, semantic={"verdict": "user_selected", "method": "manual"}, reasons=[])
    rec = project.completed_scenes[1]
    assert rec.metadata["video_id"] == "B" and rec.metadata["start_offset_sec"] == 12.0
    assert rec.metadata["needs_review"] is False and rec.metadata["edited"]["previous"]["video_id"] == "A"
    assert rec.source_info["url_with_timestamp"].endswith("t=12s")
    assert Path(rec.video_path).name == "scene_002.mp4" and not out_tmp.exists()
    coord._save_project_state.assert_called()


def test_rerender_backs_up_and_enqueues(tmp_path):
    ed, coord, project = _editor(tmp_path)
    temp = tmp_path / "temp" / "p1"
    temp.mkdir(parents=True)
    (temp / "scene_001.mp4").write_bytes(b"x")
    render = tmp_path / "render"
    (render / "parts").mkdir(parents=True)
    (render / "p1_final.mp4").write_bytes(b"x")
    (render / "project_state.json").write_text("{}")
    coord.enqueue_project.return_value = {"status": "started"}
    res = ed.rerender("p1")
    bk = Path(res["backup_dir"])
    assert (bk / "temp_scenes" / "scene_001.mp4").exists() and not (temp / "scene_001.mp4").exists()
    assert (bk / "render" / "p1_final.mp4").exists() and not (render / "p1_final.mp4").exists()
    assert (render / "project_state.json").exists()  # state is kept (copied, not moved)
    coord.enqueue_project.assert_called_once_with(project_id="p1", resume=True)


def test_scene_editor_api_returns_409_for_unknown_project(tmp_path):
    from fastapi.testclient import TestClient
    from autovideo.api.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.post("/api/projects/does_not_exist/scenes/SCENE_001/redo")
    assert r.status_code == 409
    r = client.get("/api/projects/does_not_exist/scene-jobs")
    assert r.status_code == 200 and r.json()["state"] == "idle"


# ------------------------------------------------------------------ keep-if-better + online augmentation
from autovideo.footage.online_augment import AugmentResult  # noqa: E402


def _repick_setup(tmp_path, prev_score):
    ed, coord, project = _editor(tmp_path)
    rec = project.completed_scenes[1]
    rec.metadata["semantic_check"] = {"verdict": "fail", "score": prev_score, "method": "llm_choose_best"}
    sc = SimpleNamespace(scene_id="S2", visual_prompt="v", keywords=SimpleNamespace(en=["hyena chasing zebra"]))
    return ed, project, sc, rec


def _pick(score, accepted):
    p = {"path": Path("B.mp4"), "sourced": None, "offset": 3.0,
         "semantic": {"verdict": "pass" if accepted else "fail", "score": score}, "library": {"video_id": "B"}}
    return (p, None) if accepted else (None, p)


def _patches(ed, sc, rec, picks, online=None, allowed=True):
    """picks: list of pick_library_window return values, consumed in order (1st = library, 2nd = after online)."""
    import contextlib
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(ed, "_scene_ctx", return_value=(2, sc, rec)))
    stack.enter_context(patch.object(ed, "_library", return_value=(MagicMock(), MagicMock(confusers=[]), MagicMock())))
    stack.enter_context(patch.object(ed, "_library_fingerprint", return_value="fp1"))
    stack.enter_context(patch.object(ed, "_online_allowed", return_value=allowed))
    stack.enter_context(patch("autovideo.footage.scene_picker.pick_library_window", side_effect=list(picks)))
    sa = stack.enter_context(patch("autovideo.footage.online_augment.search_and_add",
                                   return_value=online or AugmentResult(queries=["q"])))
    recut = stack.enter_context(patch.object(ed, "_recut"))
    return stack, sa, recut


@pytest.mark.parametrize("prev,new,accepted,expect_kept", [
    (3.0, 2.0, False, True),    # worse -> keep current footage
    (3.0, 3.0, False, True),    # equal -> keep (no churn)
    (3.0, 4.0, False, False),   # better (still below threshold) -> replace
    (3.0, 7.0, True, False),    # passed threshold -> replace
])
def test_redo_only_replaces_when_better(tmp_path, prev, new, accepted, expect_kept):
    ed, project, sc, rec = _repick_setup(tmp_path, prev)
    stack, sa, recut = _patches(ed, sc, rec, [_pick(new, accepted)], allowed=False)
    with stack:
        res = ed._auto_repick(project, "S2")
    assert bool(res.get("kept")) is expect_kept
    assert recut.called is (not expect_kept)
    sa.assert_not_called()


def test_online_search_runs_when_library_has_nothing_and_new_footage_is_used(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    online = AugmentResult(queries=["spotted hyena chasing zebra"], added=["NEW1", "NEW2"])
    stack, sa, recut = _patches(ed, sc, rec, [(None, None), _pick(8.0, True)], online=online)
    with stack:
        res = ed._auto_repick(project, "S2")
    sa.assert_called_once()
    assert res.get("kept") is None and res["online"]["added"] == ["NEW1", "NEW2"]
    assert recut.called


def test_online_search_runs_when_library_pick_is_below_threshold(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    online = AugmentResult(queries=["q"], added=["NEW1"])
    stack, sa, recut = _patches(ed, sc, rec, [_pick(4.0, False), _pick(6.0, True)], online=online)
    with stack:
        res = ed._auto_repick(project, "S2")
    sa.assert_called_once()
    assert res["score"] == 6.0 and recut.call_count == 1   # recut once, with the better online footage


def test_online_nothing_new_keeps_and_marks_exhausted(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    stack, sa, recut = _patches(ed, sc, rec, [(None, None)], online=AugmentResult(queries=["q"], skipped=8))
    with stack:
        res = ed._auto_repick(project, "S2")
        assert ed._auto_exhausted(rec, "fp1") is True
    assert res["kept"] is True and "tìm online" in res["reason"] and not recut.called


def test_youtube_block_is_not_treated_as_exhausted_and_stops_further_online(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    state = {"blocked": False}
    stack, sa, recut = _patches(ed, sc, rec, [(None, None)], online=AugmentResult(queries=["q"], blocked=True))
    with stack:
        res = ed._auto_repick(project, "S2", state)
        assert ed._auto_exhausted(rec, "fp1") is False      # will be retried later
    assert state["blocked"] is True and "chặn" in res["reason"]
    # a second scene in the same batch must not hit YouTube again
    stack2, sa2, _ = _patches(ed, sc, rec, [(None, None)])
    with stack2:
        ed._auto_repick(project, "S2", state)
    sa2.assert_not_called()


def test_library_already_exhausted_skips_library_llm_and_goes_online(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    rec.metadata["auto_redo"] = {"result": "kept", "fingerprint": "fp1", "online": {"tried": False, "blocked": True}}
    online = AugmentResult(queries=["q"], added=["NEW1"])
    stack, sa, recut = _patches(ed, sc, rec, [_pick(7.0, True)], online=online)
    with stack:
        ed._auto_repick(project, "S2")
    sa.assert_called_once()
    assert recut.called


def test_bulk_redo_skips_only_fully_exhausted_scenes(tmp_path):
    from autovideo.scene_editor import SceneEditError
    ed, coord, project = _editor(tmp_path)
    rec = project.completed_scenes[1]
    rec.metadata["auto_redo"] = {"result": "kept", "fingerprint": "fp", "online": {"tried": False}}
    with patch.object(ed, "_library_fingerprint", return_value="fp"), patch.object(ed, "_run_job") as run:
        ed.redo_flagged("p1")          # library tried but online not yet -> still eligible
    assert run.called
    rec.metadata["auto_redo"]["online"] = {"tried": True}
    with patch.object(ed, "_library_fingerprint", return_value="fp"):
        with pytest.raises(SceneEditError) as exc:
            ed.redo_flagged("p1")      # library + online both tried -> explain, don't loop
    assert "YouTube" in str(exc.value) and "Chọn footage khác" in str(exc.value)
    with patch.object(ed, "_library_fingerprint", return_value="fp"), patch.object(ed, "_run_job") as run:
        ed.redo_flagged("p1", force=True)
    assert run.called


def test_user_selected_footage_is_never_auto_replaced(tmp_path):
    from autovideo.scene_editor import SceneEditor
    rec = SimpleNamespace(metadata={"semantic_check": {"verdict": "user_selected", "method": "manual"}})
    assert SceneEditor._prev_score(rec) == 10.0


def test_accept_scene_clears_flag(tmp_path):
    ed, coord, project = _editor(tmp_path)
    rec = project.completed_scenes[1]
    rec.metadata["review_reasons"] = ["semantic_below_threshold(score=3.0)"]
    with patch.object(ed, "_scene_ctx", return_value=(2, None, rec)):
        res = ed.accept_scene("p1", "S2")
    assert res["still_flagged"] == 0
    assert rec.metadata["needs_review"] is False
    assert rec.metadata["review_accepted"]["previous_reasons"] == ["semantic_below_threshold(score=3.0)"]
    coord._save_project_state.assert_called()


# ------------------------------------------------------------------ search_and_add (online augmentation)
def test_judge_timeout_never_counts_as_pass_and_skips_online(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    unverified = {"path": Path("B.mp4"), "sourced": None, "offset": 3.0,
                  "semantic": {"verdict": "unavailable", "score": 0.31, "reason": "timed out"}, "library": {"video_id": "B"}}
    stack, sa, recut = _patches(ed, sc, rec, [(unverified, None)])
    with stack:
        res = ed._auto_repick(project, "S2")
        assert ed._auto_exhausted(rec, "fp1") is False     # will be retried
    assert res["kept"] is True and res.get("judge_unavailable") is True
    assert not recut.called and not sa.called


def test_judge_timeout_after_online_download_does_not_replace(tmp_path):
    ed, project, sc, rec = _repick_setup(tmp_path, 3.0)
    unverified = {"path": Path("N.mp4"), "sourced": None, "offset": 1.0,
                  "semantic": {"verdict": "unavailable", "score": 0.31}, "library": {"video_id": "NEW1"}}
    stack, sa, recut = _patches(ed, sc, rec, [(None, None), (unverified, None)],
                                online=AugmentResult(queries=["q"], added=["NEW1"]))
    with stack:
        res = ed._auto_repick(project, "S2")
    assert res["kept"] is True and not recut.called


def test_choose_best_retries_once_on_timeout():
    j = SemanticFootageJudge(enabled=True, api_key="k", model="m", min_score=5)
    calls = iter([RuntimeError("Judge request timed out"), '{"scores": {"A": 7}, "unusable": [], "best": "A"}'])

    def fake(prompt, images):
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", side_effect=fake):
        r = j.choose_best([{"path": "x", "start": 0, "duration": 5}], "n", "p", "spotted hyena")
    assert r["verdict"] == "pass" and j.calls == 2


def _fake_lib(tmp_path, known=("OLD",)):
    lib = MagicMock()
    lib.videos = {k: object() for k in known}
    lib.load_catalog.return_value = {}
    lib.raw_dir = tmp_path
    lib.index_video.return_value = object()
    return lib


def test_search_and_add_filters_and_caps_downloads(tmp_path):
    from autovideo.footage.online_augment import search_and_add
    lib = _fake_lib(tmp_path)
    entries = [
        {"id": "OLD", "title": "Spotted hyena hunting", "duration": 60},             # already in library
        {"id": "S1", "title": "Striped Hyena walking", "duration": 60},              # look-alike species
        {"id": "S2", "title": "Spotted hyena cartoon for kids", "duration": 60},     # negative term
        {"id": "S3", "title": "Spotted hyena chase", "duration": 5},                 # too short
        {"id": "G1", "title": "Spotted hyena chasing zebra", "duration": 120},
        {"id": "G2", "title": "Hyena clan hunting wildebeest", "duration": 300},
        {"id": "G3", "title": "Spotted hyenas at a kill", "duration": 200},
    ]
    dl = MagicMock()
    dl.get_video_info.return_value = {"entries": entries}
    dl._download_and_verify.side_effect = lambda url, vid, d: tmp_path / f"universal_{vid}.mp4"
    res = search_and_add(lib, ["spotted hyena chasing zebra"], "spotted hyena", confusers=["striped hyena"],
                         downloader=dl, max_new=2)
    assert res.added == ["G1", "G2"]
    assert dl._download_and_verify.call_count == 2
    assert "ytsearch8:" in dl.get_video_info.call_args[0][0]
    assert lib.register.call_count == 2


def test_search_and_add_stops_on_youtube_block(tmp_path):
    from autovideo.footage.online_augment import search_and_add
    lib = _fake_lib(tmp_path)
    dl = MagicMock()
    dl.get_video_info.side_effect = YouTubeBlockedError("Sign in to confirm you're not a bot")
    res = search_and_add(lib, ["q1", "q2"], "spotted hyena", downloader=dl)
    assert res.blocked and dl.get_video_info.call_count == 1 and res.added == []


from autovideo.sourcing.universal import YouTubeBlockedError  # noqa: E402
