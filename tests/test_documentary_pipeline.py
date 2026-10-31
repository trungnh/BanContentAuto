"""
Test suite for Documentary Pipeline & Scene Splitter (CD Media benchmark style).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from autovideo.core.binary_manager import BinaryManager
from autovideo.production.documentary_assembler import (
    DocumentaryAssembler,
    DocumentaryAssemblerConfig,
    DocumentarySceneItem,
)
from autovideo.script.prompts import DOCUMENTARY_RULES, PersonaRegistry
from autovideo.sourcing.scene_splitter import SceneSplitter, ShotInfo


def test_documentary_prompts_and_persona():
    """Verify documentary rules and HistoricalStoryteller + NatureStoryteller persona registration."""
    assert "CÔNG THỨC PHIM TÀI LIỆU LỊCH SỬ" in DOCUMENTARY_RULES
    storyteller = PersonaRegistry.get_historical_storyteller()
    assert storyteller.agent_id == "historical_storyteller"
    assert "Đạo diễn & Biên kịch Phim tài liệu" in storyteller.system_prompt
    
    nature = PersonaRegistry.get_nature_storyteller()
    assert nature.agent_id == "nature_storyteller"
    assert "Đạo diễn Phóng sự Thiên nhiên" in nature.system_prompt

    all_personas = PersonaRegistry.get_all_personas()
    assert "historical_storyteller" in all_personas
    assert "nature_storyteller" in all_personas


def test_scene_splitter_logic(tmp_path: Path):
    """Test ShotInfo dataclass and manifest serialization."""
    shot = ShotInfo(
        shot_id="shot_001",
        file_path=tmp_path / "shot_001.mp4",
        duration_sec=4.25,
        width=1920,
        height=1080,
        thumbnail_path=tmp_path / "shot_001.jpg",
        tags=["battle", "mongol"],
    )
    d = shot.to_dict()
    assert d["shot_id"] == "shot_001"
    assert d["duration_sec"] == 4.25
    assert d["width"] == 1920
    assert "battle" in d["tags"]


def test_documentary_assembler_filter_generation():
    """Verify FFmpeg filter chain generation for transformative Fair Use and Virtual Camera."""
    config = DocumentaryAssemblerConfig(
        target_width=1920,
        target_height=1080,
        target_fps=30,
        contrast=1.15,
        apply_vignette=True,
        apply_color_grade=True,
    )
    assembler = DocumentaryAssembler(config=config)
    vf_wide = assembler._build_video_filter(duration_sec=5.0, camera_scale="Wide")
    assert "scale=1920:1080" in vf_wide
    assert "crop=1920:1080" in vf_wide
    assert "vignette" in vf_wide
    assert "zoompan" in vf_wide
    assert "contrast=1.15" in vf_wide

    vf_closeup = assembler._build_video_filter(duration_sec=5.0, camera_scale="Closeup")
    assert "1.38" in vf_closeup

    vf_pan = assembler._build_video_filter(duration_sec=5.0, camera_scale="Medium", virtual_reframe="pan_left_right")
    assert "iw-iw/zoom" in vf_pan

    vf_flip = assembler._build_video_filter(duration_sec=5.0, camera_scale="Wide", virtual_reframe="flip_slowmo")
    assert "hflip" in vf_flip


def test_scene_cluster_model_attributes():
    """Verify Scene model continuity and clustering attributes."""
    from autovideo.script.pipeline import Scene

    scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        cluster_id="CLUSTER_ZOO",
        environment_id="zoo_cage_night",
        camera_scale="Closeup",
        virtual_reframe="top_closeup",
        text="Benjamin gục ngã vì lạnh.",
        duration_sec=5.0,
        word_count=6,
        visual_prompt="Close up on Tasmanian tiger eyes",
    )
    assert scene.cluster_id == "CLUSTER_ZOO"
    assert scene.environment_id == "zoo_cage_night"
    assert scene.camera_scale == "Closeup"
    assert scene.virtual_reframe == "top_closeup"


def test_binary_manager_get_binary_path():
    """Verify BinaryManager helper returns resolved Path."""
    bm = BinaryManager()
    ffmpeg_path = bm.get_binary_path("ffmpeg")
    assert isinstance(ffmpeg_path, Path)
    assert ffmpeg_path.exists()
