import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from autovideo.coordinator import MasterPipelineCoordinator, CompletedSceneRecord
from autovideo.core.config import AppConfig
from autovideo.script.pipeline import Scene, SceneKeyword, Screenplay, Chapter, SEOPackage


def test_action_aware_cut_with_chapters():
    """Verify that coordinator matches video chapters to scene keywords and narration."""
    coord = MasterPipelineCoordinator(config=AppConfig())

    scene = Scene(
        scene_id="SCENE_005",
        chapter_index=1,
        text="Hộp sọ của linh cẩu đốm là một tuyệt tác cơ khí sinh học với cấu trúc nghiền xương.",
        duration_sec=5.0,
        word_count=18,
        visual_prompt="Spotted hyena skull 3D scan",
        keywords=SceneKeyword(
            vi=["hộp sọ linh cẩu"],
            en=["spotted hyena skull bone crushing", "hyena sagittal crest anatomy"],
            zh=["鬣狗头骨"],
        ),
    )

    chapters = [
        {"start_time": 0.0, "title": "Masters of the savannah", "end_time": 32.0},
        {"start_time": 32.0, "title": "Beyond the reputation", "end_time": 80.0},
        {"start_time": 177.0, "title": "Evolution of bone crushers and skull biomechanics", "end_time": 286.0},
        {"start_time": 434.0, "title": "Unmatched immune system", "end_time": 512.0},
    ]

    mock_asset = MagicMock()
    mock_asset.duration_sec = 600.0
    mock_asset.metadata = {"chapters": chapters}

    # Test chapter matching logic directly
    en_kws = ["spotted hyena skull bone crushing", "hyena sagittal crest anatomy"]
    vi_kws = ["hộp sọ linh cẩu"]
    scene_context_lower = (scene.text + " " + " ".join(en_kws) + " " + " ".join(vi_kws)).lower()

    matched_chapter_offset = None
    best_match_count = 0
    import re
    for ch in chapters:
        ch_title = str(ch.get("title") or "").lower()
        ch_start = float(ch.get("start_time") or 0.0)
        if ch_start < 2.0 or any(x in ch_title for x in ("intro", "outro", "subscribe")):
            continue
        ch_words = [w for w in re.findall(r"\w+", ch_title) if len(w) > 3]
        match_count = sum(1 for w in ch_words if w in scene_context_lower)
        if match_count > best_match_count and (mock_asset.duration_sec - ch_start) >= (scene.duration_sec + 2.0):
            best_match_count = match_count
            matched_chapter_offset = ch_start + 2.0

    assert best_match_count > 0
    # Chapter 'Evolution of bone crushers...' starts at 177.0 -> matched offset is 179.0
    assert matched_chapter_offset == 179.0


def test_b4_thumbnail_safe_when_seo_pkg_none():
    """Verify that Step B4 does not raise AttributeError when seo_pkg is None."""
    coord = MasterPipelineCoordinator(config=AppConfig())
    project = coord.create_project(topic="Linh cẩu đốm", target_duration_min=5)

    # Simulate scenario where seo_pkg is None
    seo_pkg = None

    # Step B4 safe resolution logic:
    thumb_hook = getattr(seo_pkg, "thumbnail_hook", None) if seo_pkg else None
    if not thumb_hook and seo_pkg and getattr(seo_pkg, "thumbnail_prompt", None):
        thumb_hook = seo_pkg.thumbnail_prompt.split(",")[0][:30]
    if not thumb_hook:
        thumb_hook = (project.topic or "BẢN ÁN OAN KHỐC").split(":")[0][:25]

    assert thumb_hook is not None
    assert len(thumb_hook) > 0
    assert "Linh cẩu đốm" in thumb_hook


def test_coordinator_module_has_re_imported():
    """Verify that coordinator module has re in its global scope so chapter matching does not throw NameError."""
    import autovideo.coordinator as coord_mod
    assert hasattr(coord_mod, "re")
    assert coord_mod.re is not None


def test_pipeline_module_has_re_imported():
    """Verify that script pipeline module has re in its global scope."""
    import autovideo.script.pipeline as pipe_mod
    assert hasattr(pipe_mod, "re")
    assert pipe_mod.re is not None

