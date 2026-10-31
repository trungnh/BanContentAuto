"""
Unit and integration tests for Visual Quality Inspector & Natural Sourcing Contract.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from autovideo.coordinator import MasterPipelineCoordinator
from autovideo.production.visual_inspector import VisualQualityInspector
from autovideo.script.pipeline import Scene, SceneKeyword


def test_inspect_frame_black_detection():
    """Verify that completely black or unlit frames are flagged."""
    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    res = VisualQualityInspector.inspect_frame(black_frame)
    assert not res.is_clean
    assert res.is_black
    assert any("black" in d for d in res.defects)


def test_inspect_frame_ui_screen_detection():
    """Verify that monochromatic flat screens (presentations, browser UI) are flagged."""
    # Create flat UI screen (e.g. Facebook white/blue background with small box)
    ui_frame = np.full((720, 1280, 3), 245, dtype=np.uint8)
    # Add small toolbar
    ui_frame[:60, :] = [180, 80, 20]
    res = VisualQualityInspector.inspect_frame(ui_frame)
    assert not res.is_clean
    assert res.is_ui_screen
    assert any("ui_or_screen_capture" in d for d in res.defects)


def test_inspect_frame_natural_clean():
    """Verify that natural gradients (landscape/wildlife) pass as clean."""
    # Natural gradient across image
    x = np.linspace(50, 180, 1280, dtype=np.uint8)
    y = np.linspace(60, 200, 720, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    natural_frame = cv2.merge([xx, yy, ((xx.astype(int) + yy.astype(int)) // 2).astype(np.uint8)])
    res = VisualQualityInspector.inspect_frame(natural_frame)
    assert res.is_clean
    assert not res.is_black
    assert not res.is_ui_screen
    assert not res.has_subtitles


def test_inspect_frame_subtitles_detection():
    """Verify that high-contrast horizontal text strokes in the lower third are flagged."""
    frame = np.full((1080, 1920, 3), 60, dtype=np.uint8)
    # Render simulated subtitle text in lower third (y ~ 880-920)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, "SPOTTED HYENAS HUNT IN CLANS", (400, 920), font, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
    res = VisualQualityInspector.inspect_frame(frame)
    assert not res.is_clean
    assert res.has_subtitles
    assert any("burned_in_subtitles" in d for d in res.defects)


def test_build_natural_query():
    """Verify clean, unquoted, non-duplicative search query construction."""
    # 1. When keyword already has anchor animal, do not duplicate
    q1 = MasterPipelineCoordinator._build_natural_query("hyena snout snarling closeup", "spotted hyena")
    assert q1 == "hyena snout snarling closeup"
    assert '"' not in q1

    # 2. When keyword lacks anchor, prepend anchor naturally without quotes
    q2 = MasterPipelineCoordinator._build_natural_query("crushing bone teeth closeup", "spotted hyena")
    assert q2 == "spotted hyena crushing bone teeth closeup"
    assert '"' not in q2

    # 3. Strip quotes from incoming keywords
    q3 = MasterPipelineCoordinator._build_natural_query('"african savanna dusk"', "spotted hyena")
    assert q3 == "spotted hyena african savanna dusk"
    assert '"' not in q3


def test_calculate_action_offset_golden_ratio():
    """Verify golden ratio offset computation for long and short footage."""
    sc = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Introduction to spotted hyenas",
        visual_prompt="Spotted hyenas roaming savanna",
        duration_sec=4.0,
        word_count=12,
        word_budget_status="optimal",
    )
    # Long video (100s) -> golden ratio (20% = 20s)
    off_long = MasterPipelineCoordinator._calculate_action_offset(
        scene=sc,
        sourced_asset=None,
        source_dur=100.0,
        usage_count=0,
        en_kws=["hyena"],
        vi_kws=["linh cẩu"],
    )
    assert 18.0 <= off_long <= 22.0

    # Medium video (40s) -> 7.0s
    off_med = MasterPipelineCoordinator._calculate_action_offset(
        scene=sc,
        sourced_asset=None,
        source_dur=40.0,
        usage_count=0,
        en_kws=["hyena"],
        vi_kws=["linh cẩu"],
    )
    assert off_med == 7.0


def test_calculate_action_offset_chapter_matching():
    """Verify intelligent chapter match when chapter titles match scene context."""
    sc = Scene(
        scene_id="SCENE_002",
        chapter_index=1,
        text="The bone crushing bite force of hyena skull",
        visual_prompt="Hyena biting bone close up",
        duration_sec=5.0,
        word_count=15,
        word_budget_status="optimal",
    )
    mock_asset = MagicMock()
    mock_asset.metadata = {
        "chapters": [
            {"title": "Introduction and Habitat", "start_time": 0.0},
            {"title": "Bone Crushing Bite Force Analysis", "start_time": 45.0},
            {"title": "Social Clan Structure", "start_time": 90.0},
        ]
    }
    off = MasterPipelineCoordinator._calculate_action_offset(
        scene=sc,
        sourced_asset=mock_asset,
        source_dur=150.0,
        usage_count=0,
        en_kws=["hyena bite force skull"],
        vi_kws=["linh cẩu lực cắn"],
    )
    # Matched chapter 2 at 45.0 + 2.0 = 47.0s
    assert off == 47.0


def test_sourcing_anchor_rejection_contract(tmp_path):
    """Verify that off-topic candidates (Fennec fox, Castle) are strictly rejected when subject anchor is provided."""
    from autovideo.core.config import AppConfig
    from autovideo.sourcing.universal import UniversalDownloader

    cfg = AppConfig()
    dl = UniversalDownloader(cfg)

    # Mock multi-result search with off-topic 4K videos vs on-topic video
    mock_entries = [
        {
            "id": "fennec_fox_4k",
            "title": "A Young Fennec Fox's Cub Eating In A Bed Of Hays! 4k",
            "uploader": "Animal 4K",
            "duration": 25.0,
            "height": 2160,
            "width": 3840,
        },
        {
            "id": "castle_italy",
            "title": "The Castle of Rossena: Historic Italian Fortress",
            "uploader": "History Travel",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,
        },
        {
            "id": "real_hyena",
            "title": "Spotted Hyenas Hunting in the African Savanna",
            "uploader": "Wild Safari",
            "duration": 35.0,
            "height": 1080,
            "width": 1920,
        },
    ]

    with patch.object(dl, "get_video_info", return_value={"entries": mock_entries}), \
         patch.object(dl, "_download_and_verify", return_value=tmp_path / "universal_real_hyena.mp4"):
        info = dl.download(
            url="ytsearch5:spotted hyena savanna",
            output_dir=tmp_path,
            enforce_duration=True,
            subject_anchor="spotted hyena",
        )
        # Sourcing MUST pick the authentic spotted hyena video, rejecting 4K fennec fox and castle
        assert info.video_id == "real_hyena"

