"""
Tests for Subtitle API endpoints and project burning flow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.config import AppConfig
from autovideo.coordinator import MasterPipelineCoordinator, ProjectState


@pytest.fixture
def client_and_coord(tmp_path):
    config = AppConfig.from_base_dir(tmp_path)
    coord = MasterPipelineCoordinator(config=config)
    app = create_app(config=config, coordinator=coord)
    client = TestClient(app)
    return client, coord, tmp_path


def test_list_subtitle_presets(client_and_coord):
    client, coord, _ = client_and_coord
    res = client.get("/api/subtitles/presets")
    assert res.status_code == 200
    data = res.json()
    assert "presets" in data
    assert "cinematic_white" in data["presets"]
    assert "yellow_spotlight" in data["presets"]
    assert "boxed_translucent" in data["presets"]


def test_create_project_with_subtitles(client_and_coord):
    client, coord, _ = client_and_coord
    payload = {
        "topic": "Test Subtitle Project",
        "skill_id": "nature-wildlife-survival",
        "target_duration_min": 5,
        "subtitles_enabled": True,
        "subtitle_preset": "yellow_spotlight",
    }
    res = client.post("/api/projects/create", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["subtitles_enabled"] is True
    assert data["subtitle_preset"] == "yellow_spotlight"


def test_get_subtitles_endpoint(client_and_coord):
    client, coord, tmp_path = client_and_coord
    p = coord.get_or_create_project("Test Sub", project_id="proj_sub1")
    
    # Create fake srt file
    proj_dir = coord.config.paths.get_project_render_dir("proj_sub1")
    proj_dir.mkdir(parents=True, exist_ok=True)
    srt_p = proj_dir / "proj_sub1_subtitles.srt"
    srt_p.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello World\n", encoding="utf-8")
    
    res = client.get("/api/projects/proj_sub1/subtitles")
    assert res.status_code == 200
    data = res.json()
    assert data["has_subtitles"] is True
    assert "Hello World" in data["srt_content"]


def test_burn_subtitles_endpoint(client_and_coord):
    client, coord, tmp_path = client_and_coord
    p = coord.get_or_create_project("Test Sub", project_id="proj_sub2")
    
    proj_dir = coord.config.paths.get_project_render_dir("proj_sub2")
    proj_dir.mkdir(parents=True, exist_ok=True)
    fake_vid = proj_dir / "proj_sub2_final.mp4"
    fake_vid.write_bytes(b"dummy_video_bytes")
    p.final_video_path = str(fake_vid)
    
    with patch("autovideo.production.subtitle_generator.SubtitleGenerator.generate_subtitles_for_scenes") as mock_gen, \
         patch("autovideo.production.subtitle_generator.SubtitleGenerator.burn_subtitles_to_video") as mock_burn:
        mock_gen.return_value = (proj_dir / "sub.ass", proj_dir / "sub.srt")
        (proj_dir / "sub.ass").write_text("dummy ass")
        (proj_dir / "sub.srt").write_text("dummy srt")
        
        def fake_burn(input_video_path, subtitle_ass_path, output_video_path, **kwargs):
            output_video_path.write_bytes(b"burned_video")
            return output_video_path
        mock_burn.side_effect = fake_burn
        
        res = client.post("/api/projects/proj_sub2/subtitles/burn", json={"preset": "boxed_translucent", "margin_v": 75})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["subtitle_preset"] == "boxed_translucent"
        assert p.subtitle_preset == "boxed_translucent"
        # Check custom_margin_v was passed to generate_subtitles_for_scenes
        _, kwargs = mock_gen.call_args
        assert kwargs.get("custom_margin_v") == 75


def test_settings_subtitle_margin_v(client_and_coord):
    client, coord, _ = client_and_coord
    res = client.get("/api/system/settings")
    assert res.status_code == 200
    data = res.json()
    assert "subtitle_margin_v" in data
    assert data["subtitle_margin_v"] == 55

    # Update subtitle_margin_v
    save_res = client.post("/api/system/settings", json={"subtitle_margin_v": 90})
    assert save_res.status_code == 200
    updated_data = save_res.json()["settings"]
    assert updated_data["subtitle_margin_v"] == 90
    assert coord.config.subtitles.margin_v == 90
