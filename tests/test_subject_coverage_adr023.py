"""
ADR-023 tests: LLM subject resolution (no generic anchors), library coverage gate with upfront online fetch,
per-scene online augmentation in the pipeline, stricter last resort, small-logo tolerance.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from autovideo.footage.subject_resolver import GENERIC_ANCHORS, SubjectResolver, parse_response


# ------------------------------------------------------------------ F1 subject resolution
def test_parse_response_accepts_specific_and_rejects_generic():
    good = parse_response('{"anchor": "Sperm Whale", "aliases": ["cachalot"], "confusers": ["humpback whale", "sperm whale"]}')
    assert good["anchor"] == "sperm whale" and good["aliases"] == ["cachalot"]
    assert good["confusers"] == ["humpback whale"]          # anchor itself is dropped from confusers
    for generic in ("wildlife animal", "animal", "documentary"):
        with pytest.raises(ValueError):
            parse_response(f'{{"anchor": "{generic}"}}')


def test_resolver_uses_llm_once_then_cache(tmp_path):
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return '{"anchor": "sperm whale", "aliases": ["cachalot"], "confusers": ["humpback whale"]}'

    r = SubjectResolver(tmp_path / "subjects.json", llm_call=llm, fallback=lambda t, s: "wildlife animal")
    a = r.resolve("Tại sao bạn sẽ chẳng bao giờ muốn chạm trán một con cá nhà táng", "nature-wildlife-survival")
    b = r.resolve("Tại sao bạn sẽ chẳng bao giờ muốn chạm trán một con cá nhà táng", "nature-wildlife-survival")
    assert a["anchor"] == b["anchor"] == "sperm whale" and a["source"] == "llm"
    assert len(calls) == 1
    assert "cá nhà táng" in calls[0]


def test_resolver_falls_back_and_flags_generic_when_llm_fails(tmp_path):
    def llm(prompt):
        raise RuntimeError("9router down")
    r = SubjectResolver(tmp_path / "s.json", llm_call=llm, fallback=lambda t, s: "wildlife animal")
    res = r.resolve("chủ đề lạ", "nature-wildlife-survival")
    assert res["source"] == "map" and res["generic"] is True
    # a failed/generic result is never cached as final -> next run retries the LLM
    assert not (tmp_path / "s.json").exists()


def test_fallback_map_knows_sperm_whale_and_does_not_confuse_whale_with_elephant():
    from autovideo.coordinator import MasterPipelineCoordinator as M
    f = lambda t: M._extract_subject_anchor(None, t, "nature-wildlife-survival")  # noqa: E731
    assert f("Tại sao bạn sẽ chẳng bao giờ muốn chạm trán một con cá nhà táng") == "sperm whale"
    assert f("Cá voi xanh khổng lồ") == "blue whale"
    assert f("Bí ẩn cá voi") == "whale"            # previously 'voi' matched first -> 'african elephant'
    assert f("Đàn voi châu Phi") == "african elephant"
    assert f("Linh cẩu đốm") == "spotted hyena"


def test_scene_editor_uses_resolved_subject():
    from autovideo.scene_editor import SceneEditor
    coord = MagicMock()
    coord._resolve_subject.return_value = {"anchor": "sperm whale", "confusers": ["humpback whale"]}
    ed = SceneEditor(coord)
    assert ed._anchor(SimpleNamespace(topic="cá nhà táng", skill_id="x")) == "sperm whale"


# ------------------------------------------------------------------ F2 coverage gate
def _coord_for_coverage(tmp_path):
    from autovideo.coordinator import MasterPipelineCoordinator
    coord = MasterPipelineCoordinator.__new__(MasterPipelineCoordinator)
    coord.emit_event = MagicMock()
    return coord


def _video(title):
    return SimpleNamespace(entry=SimpleNamespace(text=lambda t=title: t))


def test_coverage_gate_skips_download_when_library_covers_subject(tmp_path):
    coord = _coord_for_coverage(tmp_path)
    matcher = MagicMock(confusers=[])
    matcher.eligible_videos.return_value = [_video(f"Sperm whale clip {i}") for i in range(9)]
    with patch("autovideo.footage.online_augment.search_and_add") as sa:
        added = coord._ensure_library_coverage("p", [], MagicMock(), matcher, "sperm whale", {"blocked": False})
    assert added == 0 and not sa.called


def test_coverage_gate_fetches_subject_footage_when_library_is_about_something_else(tmp_path):
    from autovideo.footage.online_augment import AugmentResult
    coord = _coord_for_coverage(tmp_path)
    matcher = MagicMock(confusers=["humpback whale"])
    # 20 hyena videos that matched a generic anchor are NOT coverage for 'sperm whale'
    matcher.eligible_videos.return_value = [_video("Hyena mom and her cubs")] * 20 + [_video("Sperm whale hunting")]
    scenes = [SimpleNamespace(keywords=SimpleNamespace(en=["sperm whale tail fluke dive"]))]
    state = {"blocked": False}
    with patch("autovideo.footage.online_augment.search_and_add",
               return_value=AugmentResult(queries=["q"], added=["A", "B", "C"])) as sa:
        added = coord._ensure_library_coverage("p", scenes, MagicMock(), matcher, "sperm whale", state)
    assert added == 3
    queries = sa.call_args[0][1]
    assert all("sperm whale" in q for q in queries) and "sperm whale tail fluke dive" in queries
    assert sa.call_args[1]["confusers"] == ["humpback whale"]
    assert sa.call_args[1]["max_new"] >= 7


def test_coverage_gate_marks_youtube_blocked(tmp_path):
    from autovideo.footage.online_augment import AugmentResult
    coord = _coord_for_coverage(tmp_path)
    matcher = MagicMock(confusers=[])
    matcher.eligible_videos.return_value = []
    state = {"blocked": False}
    with patch("autovideo.footage.online_augment.search_and_add", return_value=AugmentResult(blocked=True)):
        coord._ensure_library_coverage("p", [], MagicMock(), matcher, "sperm whale", state)
    assert state["blocked"] is True


# ------------------------------------------------------------------ F3/F4 pipeline guards
def test_pipeline_uses_resolver_online_augment_and_stricter_last_resort():
    import inspect
    import autovideo.coordinator as coord_mod
    src = inspect.getsource(coord_mod.MasterPipelineCoordinator._run_pipeline_body)
    assert "self._resolve_subject(" in src
    assert "self._ensure_library_coverage(" in src
    assert "search_and_add(" in src                          # per-scene online augmentation
    assert "footage_matcher is None" in src                 # legacy online loop only without CLIP library
    assert "with_subject_min(0.22)" not in src and "with_subject_min(0.25)" in src


# ------------------------------------------------------------------ F5 overlay tolerance
def _judge_with(payload, tmp_path):
    import json
    from autovideo.production.semantic_judge import SemanticFootageJudge
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 4096)
    j = SemanticFootageJudge(enabled=True, api_key="k", model="m", min_score=5)
    with patch.object(j, "_sample_frames", return_value=(["a", "b", "c"], [0, 1, 2])), \
         patch.object(j, "_call_ninerouter", return_value=json.dumps(payload)):
        return j.judge(v, 0.0, 5.0, "n", "p", "sperm whale")


def test_small_corner_logo_only_costs_a_point(tmp_path):
    base = {"subject_present": True, "is_real_footage": True, "overlay_text_or_watermark": False, "match_score": 7}
    r = _judge_with({**base, "small_corner_logo": True}, tmp_path)
    assert r.verdict == "pass" and r.score == 6.0
    r2 = _judge_with({**base, "overlay_text_or_watermark": True}, tmp_path)
    assert r2.verdict == "fail"                               # large captions still reject


def test_choose_best_prompt_tolerates_small_logos():
    from autovideo.production.semantic_judge import SemanticFootageJudge
    j = SemanticFootageJudge(enabled=True, api_key="k", model="m")
    captured = {}

    def fake(prompt, images):
        captured["p"] = prompt
        return '{"scores": {"A": 7}, "unusable": [], "best": "A"}'

    with patch.object(j, "_grid_image", return_value="img"), patch.object(j, "_call_ninerouter", side_effect=fake):
        j.choose_best([{"path": "x", "start": 0, "duration": 5}], "n", "p", "sperm whale")
    assert "small channel logo" in captured["p"] and "does NOT make a row unusable" in captured["p"]
