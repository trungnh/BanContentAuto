"""
Unit and Integration Tests for FastAPI Server, Coordinator & Studio Dashboard (WU-08).
Validates:
1. System Health resource probing & external binaries (REQ-PUB-02).
2. Studio Dashboard HTML delivery.
3. 1-Click Wizard project creation and status lifecycle (VAC-UI-01, VAC-UI-02).
4. Master Pipeline Coordinator end-to-end execution B1 -> B2 -> B3 -> B4.
5. Real-time Server-Sent Events (SSE) streaming.
6. Scene Mini Player MP4 and Safe-Zone Thumbnail preview endpoints (VAC-UI-03, VAC-UI-04).
7. SEO Package metadata endpoint and 1-Click YouTube publish flow.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.coordinator import (
    CompletedSceneRecord,
    MasterPipelineCoordinator,
    PipelineEvent,
    PipelineStage,
    ProjectState,
)
from autovideo.core.binary_manager import BinaryInfo, BinaryManager
from autovideo.core.config import AppConfig
from autovideo.publisher.manager import PublishResult
from autovideo.publisher.seo_packager import SEOPackage
from autovideo.publisher.youtube_uploader import UploadStatus
from autovideo.script.pipeline import Chapter, Scene, SceneKeyword, Screenplay


@pytest.fixture
def mock_app_config(tmp_path: Path) -> AppConfig:
    """Fixture providing isolated project directories."""
    cfg = AppConfig()
    cfg.paths.base_dir = tmp_path
    cfg.paths.ensure_directories()
    return cfg


@pytest.fixture
def test_client(mock_app_config: AppConfig) -> Generator[TestClient, None, None]:
    """TestClient instance configured with isolated config."""
    app = create_app(config=mock_app_config)
    with TestClient(app) as client:
        yield client


def test_system_health_endpoint(test_client: TestClient) -> None:
    """Verifies GET /api/system/health returns host resources and binary info."""
    resp = test_client.get("/api/system/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "healthy"
    assert "cpu_cores" in data
    assert "ram_used_pct" in data
    assert "disk_free_gb" in data
    assert "rolling_buffer_gb" in data
    assert "binaries" in data
    assert data["zerotts_ready"] is True


def test_serve_dashboard_html(test_client: TestClient) -> None:
    """Verifies GET / returns valid Studio Dashboard HTML."""
    resp = test_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "BANCONTENT AUTO STUDIO" in resp.text
    assert "Quick Launch Wizard" in resp.text


def test_create_project_and_status(test_client: TestClient) -> None:
    """Tests 1-Click Wizard project initialization (VAC-UI-01)."""
    payload = {
        "topic": "Điều tra thảm họa xe tải tuột dốc",
        "skill_id": "dashcam-near-misses",
        "target_duration_min": 15,
    }
    create_resp = test_client.post("/api/projects/create", json=payload)
    assert create_resp.status_code == 200
    created = create_resp.json()

    assert created["topic"] == payload["topic"]
    assert created["skill_id"] == payload["skill_id"]
    assert created["stage"] == "IDLE"
    project_id = created["project_id"]
    assert project_id.startswith("proj_")

    # Query status
    status_resp = test_client.get(f"/api/projects/{project_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["project_id"] == project_id
    assert status_data["stage"] == "IDLE"
    assert status_data["progress"] == 0.0


def test_status_not_found(test_client: TestClient) -> None:
    """Verifies 404 response for non-existent project queries."""
    resp = test_client.get("/api/projects/non_existent_id/status")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


def test_master_pipeline_coordinator_lifecycle(mock_app_config: AppConfig, tmp_path: Path) -> None:
    """
    Directly tests MasterPipelineCoordinator executing the complete 4-step pipeline:
    B1 (Script) -> B2 (TTS & Scene assembly) -> B3 (Render) -> B4 (Packaging).
    """
    coordinator = MasterPipelineCoordinator(config=mock_app_config)
    project = coordinator.get_or_create_project(
        topic="Sập kệ kho công nghiệp 15 triệu USD",
        skill_id="warehouse-fails",
        target_duration_min=5,
        project_id="test_full_pipe_001",
    )

    # Prepare dummy files to avoid real long ffmpeg encode in quick unit test
    dummy_video = tmp_path / "dummy_final.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes")

    dummy_thumb = tmp_path / "dummy_thumb.jpg"
    dummy_thumb.write_bytes(b"dummy thumbnail bytes")

    dummy_preview = tmp_path / "dummy_thumb_preview.jpg"
    dummy_preview.write_bytes(b"dummy preview bytes")

    dummy_seo = tmp_path / "dummy_seo.md"
    dummy_seo.write_text("# SEO Title", encoding="utf-8")

    # Mock B2 assembly, B3 production, and B4 packaging for deterministic fast testing
    with patch.object(coordinator, "_run_pipeline_sync") as mock_run:
        # Simulate pipeline execution
        def fake_run(project_id: str, resume: bool = True):
            p = coordinator.projects[project_id]
            coordinator.emit_event(project_id, PipelineStage.B1_SCRIPT, 20.0, "Kịch bản xong")
            p.completed_scenes.append(
                CompletedSceneRecord(
                    scene_id="SCENE_001",
                    chapter_index=1,
                    text="Xe tải trượt dốc kinh hoàng.",
                    duration_sec=4.5,
                    word_count=16,
                    word_budget_status="optimal",
                    video_path=str(dummy_video),
                    audio_path=str(dummy_video),
                    status="completed",
                )
            )
            coordinator.emit_event(project_id, PipelineStage.B2_SOURCING_TTS, 60.0, "Footage và TTS xong")
            p.final_video_path = str(dummy_video)
            coordinator.emit_event(project_id, PipelineStage.B3_RENDER, 85.0, "Render xong")
            p.thumbnail_path = str(dummy_thumb)
            p.thumbnail_preview_path = str(dummy_preview)
            p.seo_markdown_path = str(dummy_seo)
            p.seo_package = {
                "titles": ["Sự Cố Kệ Kho 15 Triệu Đô"],
                "description": "Điều tra chi tiết.",
                "hashtags": ["#WarehouseFail"],
            }
            coordinator.emit_event(project_id, PipelineStage.COMPLETE, 100.0, "Hoàn tất")

        mock_run.side_effect = fake_run

        # Execute
        asyncio.run(coordinator.run_pipeline_async("test_full_pipe_001"))

        # Verify state
        assert project.stage == PipelineStage.COMPLETE
        assert project.progress == 100.0
        assert len(project.completed_scenes) == 1
        assert project.completed_scenes[0].scene_id == "SCENE_001"
        assert project.completed_scenes[0].word_budget_status == "optimal"
        assert project.final_video_path == str(dummy_video)
        assert project.thumbnail_path == str(dummy_thumb)


def test_master_pipeline_coordinator_run_sync_execution(mock_app_config: AppConfig, tmp_path: Path) -> None:
    """
    Directly tests coordinator._run_pipeline_sync without mocking _run_pipeline_sync.
    Ensures rolling_buffer.get_buffer_size_bytes and measure_directory_bytes work during execution.
    """
    coordinator = MasterPipelineCoordinator(config=mock_app_config)
    project = coordinator.get_or_create_project(
        topic="Sập kệ kho công nghiệp 15 triệu USD",
        skill_id="warehouse-fails",
        target_duration_min=5,
        project_id="test_sync_flow_001",
    )

    from autovideo.production.chapter_builder import ProductionResult
    from autovideo.production.scene_muxer import SceneMuxResult
    from autovideo.voiceover.zerotts_adapter import SynthesisResult

    mock_scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Cú đâm cực mạnh khiến toàn bộ kệ kho rung chuyển.",
        visual_prompt="Warehouse collapse footage",
        duration_sec=5.0,
        word_count=10,
        keywords=SceneKeyword(vi=["kệ kho"], en=["warehouse"]),
    )
    mock_screenplay = Screenplay(
        title="Sập kệ kho công nghiệp",
        skill_id="warehouse-fails",
        topic="Sập kệ kho công nghiệp 15 triệu USD",
        chapters=[Chapter(chapter_index=1, title="Mở đầu", target_duration_sec=5.0, scenes=[mock_scene])],
        total_duration_sec=5.0,
        total_word_count=10,
    )

    dummy_file = tmp_path / "dummy.mp4"
    dummy_file.write_bytes(b"dummy")
    dummy_md = tmp_path / "screenplay.json"
    dummy_md.write_text("{}", encoding="utf-8")
    dummy_seo = tmp_path / "seo.md"
    dummy_seo.write_text("{}", encoding="utf-8")

    from autovideo.publisher.seo_packager import SEOPackage as PubSEOPackage
    from autovideo.script.pipeline import SEOPackage as ScriptSEOPackage

    script_seo = ScriptSEOPackage(
        titles=["Test Title"],
        description="Test Desc",
        hashtags=["#test"],
        thumbnail_prompt="Khoảnh khắc kinh hoàng, xe tải tuột dốc",
    )
    pub_seo = PubSEOPackage(
        project_id="test_sync_flow_001",
        titles=["Test Title"],
        description="Test Desc",
        tags=["test"],
        hashtags=["#test"],
    )

    synth_res = SynthesisResult(
        audio_path=dummy_file,
        duration_sec=5.0,
        duration_ms=5000,
        text="Cú đâm cực mạnh khiến toàn bộ kệ kho rung chuyển.",
        voice_id="maichi",
        sample_rate=24000,
        engine="zerotts",
    )

    prod_res = ProductionResult(
        project_id="test_sync_flow_001",
        final_video_path=dummy_file,
        total_duration_sec=5.0,
        width=1920,
        height=1080,
        fps=30.0,
        chapter_results=[],
        concat_elapsed_sec=0.1,
        total_elapsed_sec=0.2,
        resumed_chapters_count=0,
        buffer_metrics={},
    )

    from autovideo.sourcing.engine import SourcedAsset
    mock_sourced = SourcedAsset(
        scene_id="SCENE_001",
        query="test",
        file_path=dummy_file,
        duration_sec=5.0,
        width=1920,
        height=1080,
        vault_source="universal",
    )

    with patch.object(coordinator.script_brain, "generate_screenplay", return_value=(mock_screenplay, script_seo)), \
         patch.object(coordinator.script_brain, "export_artifacts", return_value=(dummy_md, dummy_seo)), \
         patch.object(coordinator.voiceover_manager, "synthesize_scene", return_value=synth_res), \
         patch.object(coordinator.sourcing_engine, "source_scene_asset", return_value=mock_sourced), \
         patch.object(coordinator.scene_muxer, "assemble_scene", return_value=SceneMuxResult(scene_id=1, project_id="test_sync_flow_001", output_path=dummy_file, duration_sec=5.0, width=1920, height=1080, fps=30.0, has_audio=True, timing_action="looped")), \
         patch("autovideo.coordinator.ProductionPipeline.run", return_value=prod_res), \
         patch.object(coordinator.publisher_manager, "prepare_publishing_package", return_value=PublishResult(project_id="test_sync_flow_001", output_dir=tmp_path, thumbnail_path=dummy_file, thumbnail_preview_path=dummy_file, seo_markdown_path=dummy_file, seo_package=pub_seo)):

        coordinator._run_pipeline_sync("test_sync_flow_001")
        assert project.stage == PipelineStage.COMPLETE
        assert project.progress == 100.0
        assert project.rolling_buffer_bytes >= 0


def test_start_pipeline_api(test_client: TestClient, tmp_path: Path) -> None:
    """Tests POST /api/projects/{id}/start trigger."""
    # Create project
    create_resp = test_client.post(
        "/api/projects/create",
        json={"topic": "Test start", "skill_id": "warehouse-fails", "target_duration_min": 5},
    )
    p_id = create_resp.json()["project_id"]

    coord: MasterPipelineCoordinator = test_client.app.state.coordinator

    # Patch run_pipeline_async so it executes quickly
    with patch.object(coord, "run_pipeline_async") as mock_async_run:
        mock_async_run.return_value = coord.projects[p_id]

        start_resp = test_client.post(f"/api/projects/{p_id}/start")
        assert start_resp.status_code == 200
        data = start_resp.json()
        assert data["status"] == "started"
        assert data["project_id"] == p_id


def test_preview_endpoints(test_client: TestClient, tmp_path: Path) -> None:
    """Tests scene video, final video, and thumbnail preview endpoints."""
    # Create project
    create_resp = test_client.post(
        "/api/projects/create",
        json={"topic": "Test preview", "skill_id": "warehouse-fails", "target_duration_min": 5},
    )
    p_id = create_resp.json()["project_id"]
    coord: MasterPipelineCoordinator = test_client.app.state.coordinator
    project = coord.projects[p_id]

    # Create dummy files
    scene_file = tmp_path / "scene_001.mp4"
    scene_file.write_bytes(b"dummy scene mp4")

    final_vid_file = tmp_path / "final.mp4"
    final_vid_file.write_bytes(b"dummy final mp4")

    thumb_file = tmp_path / "thumb_safe_zone.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xe0" + b"dummy jpeg")

    project.completed_scenes.append(
        CompletedSceneRecord(
            scene_id="SCENE_001",
            chapter_index=1,
            text="Lời thoại thử nghiệm.",
            duration_sec=4.0,
            word_count=14,
            word_budget_status="optimal",
            video_path=str(scene_file),
            audio_path=str(scene_file),
            status="completed",
        )
    )
    project.final_video_path = str(final_vid_file)
    project.thumbnail_preview_path = str(thumb_file)
    project.seo_package = {
        "titles": ["Tiêu Đề Thử Nghiệm 1"],
        "description": "Mô tả chuẩn SEO",
        "hashtags": ["#Test"],
    }

    # 1. Preview Scene MP4
    resp_scene = test_client.get(f"/api/projects/{p_id}/preview/scene/SCENE_001")
    assert resp_scene.status_code == 200
    assert "video/mp4" in resp_scene.headers["content-type"]
    assert resp_scene.content == b"dummy scene mp4"

    # Non-existent scene 404
    resp_scene_404 = test_client.get(f"/api/projects/{p_id}/preview/scene/SCENE_999")
    assert resp_scene_404.status_code == 404

    # 2. Preview Final Video
    resp_final = test_client.get(f"/api/projects/{p_id}/preview/video")
    assert resp_final.status_code == 200
    assert "video/mp4" in resp_final.headers["content-type"]

    # 3. Preview Thumbnail
    resp_thumb = test_client.get(f"/api/projects/{p_id}/preview/thumbnail")
    assert resp_thumb.status_code == 200
    assert "image/jpeg" in resp_thumb.headers["content-type"]

    # 4. SEO Endpoint
    resp_seo = test_client.get(f"/api/projects/{p_id}/seo")
    assert resp_seo.status_code == 200
    seo_data = resp_seo.json()
    assert seo_data["titles"] == ["Tiêu Đề Thử Nghiệm 1"]


def test_youtube_publish_endpoint(test_client: TestClient, tmp_path: Path) -> None:
    """Tests 1-Click YouTube Publishing endpoint (REQ-B4-02)."""
    # Create project
    create_resp = test_client.post(
        "/api/projects/create",
        json={"topic": "Test Publish", "skill_id": "warehouse-fails", "target_duration_min": 5},
    )
    p_id = create_resp.json()["project_id"]
    coord: MasterPipelineCoordinator = test_client.app.state.coordinator
    project = coord.projects[p_id]

    # Create dummy final video
    dummy_video = tmp_path / "dummy_upload.mp4"
    dummy_video.write_bytes(b"dummy video for upload")
    project.final_video_path = str(dummy_video)

    # Mock PublisherManager.publish_to_youtube
    with patch.object(coord.publisher_manager, "publish_to_youtube") as mock_publish:
        mock_publish.return_value = UploadStatus(
            status="completed",
            video_id="yt_video_123456",
            video_url="https://youtu.be/yt_video_123456",
        )

        resp = test_client.post(
            f"/api/projects/{p_id}/publish",
            json={"privacy_status": "private"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["video_id"] == "yt_video_123456"
        assert "youtu.be" in data["video_url"]


def test_sse_events_streaming(test_client: TestClient) -> None:
    """Verifies that SSE endpoint /api/projects/{id}/events streams SSE formatted data."""
    create_resp = test_client.post(
        "/api/projects/create",
        json={"topic": "Test SSE", "skill_id": "warehouse-fails", "target_duration_min": 5},
    )
    p_id = create_resp.json()["project_id"]
    coord: MasterPipelineCoordinator = test_client.app.state.coordinator

    # Emit an event
    coord.emit_event(
        project_id=p_id,
        stage=PipelineStage.COMPLETE,
        progress=100.0,
        message="Done test",
    )

    with test_client.stream("GET", f"/api/projects/{p_id}/events") as stream:
        assert stream.status_code == 200
        assert "text/event-stream" in stream.headers["content-type"]
        # Read lines from stream
        lines = []
        for line in stream.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 1:
                break

        assert any("data: " in l for l in lines)


def test_get_settings_endpoint(test_client: TestClient) -> None:
    """Verifies GET /api/system/settings returns masked settings and cache breakdown."""
    resp = test_client.get("/api/system/settings")
    assert resp.status_code == 200
    data = resp.json()

    assert "gemini_api_key_masked" in data
    assert "has_gemini_key" in data
    assert "llm_model" in data
    assert "default_voice" in data
    assert "rolling_buffer_max_gb" in data
    assert "cache_breakdown" in data
    assert "total_mb" in data["cache_breakdown"]


def test_save_settings_endpoint(test_client: TestClient, mock_app_config: AppConfig) -> None:
    """Verifies POST /api/system/settings updates settings and persists to settings.json."""
    payload = {
        "gemini_api_key": "AIzaSyTestApiKey1234567890",
        "llm_model": "gemini-1.5-pro",
        "douyin_cookie": "odin_tt=mockcookie123; sessionid=sess456",
        "jitter_min_sec": 3.0,
        "jitter_max_sec": 6.5,
        "default_voice": "vi-VN-NamMinhNeural",
        "speech_rate": 1.15,
        "target_lufs": -15.0,
        "rolling_buffer_max_gb": 10.0,
        "render_concurrency": 4,
        "clean_intermediate_parts": False,
    }

    resp = test_client.post("/api/system/settings", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True

    # Verify settings updated in memory
    settings_data = res_data["settings"]
    assert settings_data["llm_model"] == "gemini-1.5-pro"
    assert settings_data["default_voice"] == "vi-VN-NamMinhNeural"
    assert settings_data["speech_rate"] == 1.15
    assert settings_data["rolling_buffer_max_gb"] == 10.0
    assert settings_data["has_gemini_key"] is True
    assert settings_data["has_douyin_cookie"] is True

    # Verify persisted settings.json
    settings_file = mock_app_config.paths.config_dir / "settings.json"
    assert settings_file.exists()
    content = json.loads(settings_file.read_text(encoding="utf-8"))
    assert content["llm_model"] == "gemini-1.5-pro"
    assert content["render_concurrency"] == 4


def test_gemini_connectivity_endpoint(test_client: TestClient) -> None:
    """Verifies POST /api/system/settings/test-gemini validates keys."""
    # Test with mock key
    resp = test_client.post(
        "/api/system/settings/test-gemini",
        json={"api_key": "mock_api_key_for_testing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Mock" in data["message"] or "thành công" in data["message"]

    # Test with empty key
    resp_empty = test_client.post(
        "/api/system/settings/test-gemini",
        json={"api_key": ""},
    )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["success"] is False


def test_clear_cache_endpoint(test_client: TestClient, mock_app_config: AppConfig) -> None:
    """Verifies POST /api/system/cache/clear cleans temporary files and returns freed MB."""
    # Populate cache directory with dummy files
    dummy_audio = mock_app_config.paths.cache_audio_dir / "test_temp_audio.wav"
    dummy_audio.write_bytes(b"0" * 1024 * 100)  # 100 KB

    dummy_scene = mock_app_config.paths.cache_temp_scenes_dir / "test_scene_part.mp4"
    dummy_scene.write_bytes(b"1" * 1024 * 200)  # 200 KB

    resp = test_client.post("/api/system/cache/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["files_removed"] >= 2
    assert data["freed_bytes"] >= 300 * 1024

    # Verify dummy files were removed
    assert not dummy_audio.exists()
    assert not dummy_scene.exists()


def test_ninerouter_models_and_test_endpoints(test_client: TestClient) -> None:
    """Verifies POST /api/system/settings/9router/models and /test endpoints."""
    # 1. Test models retrieval with mock key
    resp = test_client.post(
        "/api/system/settings/9router/models",
        json={"base_url": "http://localhost:20128/v1", "api_key": "mock_9router_key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["models"]) >= 3
    assert any("antigravity" in m for m in data["models"])
    assert any("codex" in m for m in data["models"])

    # 2. Test connectivity endpoint
    test_resp = test_client.post(
        "/api/system/settings/9router/test",
        json={"base_url": "http://localhost:20128/v1", "api_key": "mock_9router_key"},
    )
    assert test_resp.status_code == 200
    test_data = test_resp.json()
    assert test_data["success"] is True
    assert test_data["count"] >= 3


def test_ninerouter_adapter_fallback() -> None:
    """Verifies NineRouterAdapter fails fast when key is missing or invalid (no silent fallback)."""
    import pytest
    from autovideo.script.pipeline import NineRouterAdapter

    # Fail fast on missing API key
    adapter = NineRouterAdapter(api_key="", base_url="http://localhost:20128/v1")
    with pytest.raises(ValueError, match="Chưa cấu hình 9Router API Key"):
        adapter.generate("Test prompt")


def test_tts_settings_persistence(test_client: TestClient) -> None:
    """Verifies TTS provider configurations are properly updated and masked."""
    payload = {
        "tts_primary_provider": "maziao",
        "tts_enable_fallback": True,
        "zerotts_voice": "thientam",
        "zerotts_comma_pause_ms": 250,
        "zerotts_period_pause_ms": 450,
        "maziao_api_key": "sk_test_maziao_secret_key_12345",
        "maziao_model_id": "vieten_speech",
        "maziao_voice_id": "zv_vi_sg_male_thien_tam",
        "edge_tts_voice": "vi-VN-NamMinhNeural",
    }
    save_resp = test_client.post("/api/system/settings", json=payload)
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True

    get_resp = test_client.get("/api/system/settings")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["tts_primary_provider"] == "maziao"
    assert data["tts_enable_fallback"] is True
    assert data["zerotts_voice"] == "thientam"
    assert data["zerotts_comma_pause_ms"] == 250
    assert data["zerotts_period_pause_ms"] == 450
    assert data["maziao_model_id"] == "vieten_speech"
    assert data["maziao_voice_id"] == "zv_vi_sg_male_thien_tam"
    assert data["edge_tts_voice"] == "vi-VN-NamMinhNeural"
    assert data["has_maziao_key"] is True
    assert "sk_t" in data["maziao_api_key_masked"]
    assert "2345" in data["maziao_api_key_masked"]
    assert "secret" not in data["maziao_api_key_masked"]


def test_maziao_test_endpoint(test_client: TestClient) -> None:
    """Verifies POST /api/system/settings/test-maziao handles empty and mock keys."""
    # 1. Empty key
    resp_empty = test_client.post("/api/system/settings/test-maziao", json={"api_key": ""})
    assert resp_empty.status_code == 200
    assert resp_empty.json()["success"] is False

    # 2. Mock key (offline simulated response)
    resp_mock = test_client.post("/api/system/settings/test-maziao", json={"api_key": "mock_maziao_key"})
    assert resp_mock.status_code == 200
    assert resp_mock.json()["success"] is True


def test_binaries_setup_endpoint(test_client: TestClient) -> None:
    """Verifies POST /api/system/binaries/setup executes installer without crashing."""
    with patch("autovideo.core.binary_downloader.BinaryDownloader.setup_all") as mock_setup:
        from autovideo.core.binary_downloader import SetupResult
        mock_setup.return_value = {
            "ffmpeg": SetupResult("ffmpeg", True, "bin/ffmpeg.exe", "already_present", "OK"),
            "ffprobe": SetupResult("ffprobe", True, "bin/ffprobe.exe", "already_present", "OK"),
            "yt-dlp": SetupResult("yt-dlp", True, "bin/yt-dlp.exe", "downloaded", "OK"),
            "BBDown": SetupResult("BBDown", True, "bin/BBDown.exe", "downloaded", "OK"),
        }
        resp = test_client.post("/api/system/binaries/setup")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "details" in data


def test_zerotts_voices_endpoint(test_client: TestClient) -> None:
    """Verifies GET /api/system/tts/zerotts/voices returns official voices."""
    resp = test_client.get("/api/system/tts/zerotts/voices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 8
    voice_ids = [v["id"] for v in data["voices"]]
    assert "maichi" in voice_ids
    assert "baotrang" in voice_ids
    assert "giahuy" in voice_ids


def test_zerotts_install_clone_endpoint(test_client: TestClient) -> None:
    """Verifies POST /api/system/tts/zerotts/install-clone installs a voice pack."""
    import io
    import numpy as np

    # Create dummy voice.npz content in memory
    buf = io.BytesIO()
    np.savez(buf, n_voice_queries=10, voice_emb=np.zeros((1, 10, 768), dtype=np.float32))
    buf.seek(0)

    files = {"file": ("my_cloned_voice.npz", buf.read(), "application/octet-stream")}
    resp = test_client.post("/api/system/tts/zerotts/install-clone", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "voice" in data
    assert data["voice"]["is_cloned"] is True


def test_maziao_voices_endpoint(test_client: TestClient) -> None:
    """Verifies POST /api/system/settings/maziao/voices returns categorized voices."""
    resp = test_client.post(
        "/api/system/settings/maziao/voices",
        json={"api_key": "mock_maziao_key", "base_url": "https://app.maziao.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 4
    assert any("Thiện Tâm" in v["name"] or "thien_tam" in v["id"] for v in data["voices"])


def test_list_and_queue_endpoints(test_client: TestClient) -> None:
    """Verifies GET /api/projects and GET /api/projects/queue endpoints."""
    # Create two projects
    p1 = test_client.post("/api/projects/create", json={"topic": "Dự án thử nghiệm danh sách 1", "skill_id": "warehouse-fails"}).json()
    p2 = test_client.post("/api/projects/create", json={"topic": "Dự án thử nghiệm danh sách 2", "skill_id": "plane-crashes"}).json()

    # List projects
    resp = test_client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert data["total"] >= 2
    proj_ids = [p["project_id"] for p in data["projects"]]
    assert p1["project_id"] in proj_ids
    assert p2["project_id"] in proj_ids

    # Check queue endpoint
    q_resp = test_client.get("/api/projects/queue")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert "running" in q_data
    assert "queue" in q_data
    assert "queue_length" in q_data
    assert isinstance(q_data["queue_length"], int)


def test_stop_and_delete_project_endpoints(test_client: TestClient) -> None:
    """Verifies POST /api/projects/{id}/stop and DELETE /api/projects/{id} endpoints."""
    # Create project
    p = test_client.post("/api/projects/create", json={"topic": "Dự án kiểm tra hủy và xóa", "skill_id": "warehouse-fails"}).json()
    proj_id = p["project_id"]

    # Stop project (even if not currently in loop, should return handled response)
    stop_resp = test_client.post(f"/api/projects/{proj_id}/stop")
    assert stop_resp.status_code == 200
    stop_data = stop_resp.json()
    assert stop_data["project_id"] == proj_id

    # Delete project
    del_resp = test_client.delete(f"/api/projects/{proj_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "deleted"

    # Status should now be 404
    status_resp = test_client.get(f"/api/projects/{proj_id}/status")
    assert status_resp.status_code == 404


def test_coordinator_queue_and_cancellation(mock_app_config: AppConfig, tmp_path: Path) -> None:
    """Verifies Coordinator enqueueing, sequential queueing, and cancellation logic."""
    from autovideo.coordinator import MasterPipelineCoordinator, PipelineStage

    coord = MasterPipelineCoordinator(config=mock_app_config)
    p1 = coord.create_project("Queue Video 1", "warehouse-fails", 15)
    p2 = coord.create_project("Queue Video 2", "plane-crashes", 15)

    # Simulate p1 is currently running
    p1.stage = PipelineStage.B2_SOURCING_TTS
    coord._running_project_id = p1.project_id

    # Enqueue p2 -> should be placed in queue, stage QUEUED
    res2 = coord.enqueue_project(p2.project_id, resume=True)
    assert res2["status"] == "queued"
    assert res2["queue_position"] == 1
    assert p2.stage == PipelineStage.QUEUED

    # Queue info check
    q_info = coord.get_queue_info()
    assert q_info["running"]["project_id"] == p1.project_id
    assert q_info["queue_length"] == 1
    assert q_info["queue"][0]["project_id"] == p2.project_id

    # Cancel p2 from queue
    canceled = coord.cancel_project(p2.project_id)
    assert canceled is True
    assert p2.stage == PipelineStage.CANCELLED
    assert len(coord._project_queue) == 0

    # Cancel p1 running
    canceled_p1 = coord.cancel_project(p1.project_id)
    assert canceled_p1 is True
    assert p1.project_id in coord._cancel_requested


def test_resolve_scene_source_info_attribution(mock_app_config: AppConfig) -> None:
    """Verifies that scene source information is properly resolved and formatted for studio UI."""
    from autovideo.coordinator import resolve_scene_source_info, CompletedSceneRecord, ProjectState

    # 1. YouTube footage with universal naming
    yt_scene = {
        "metadata": {"raw_asset_path": "cache/raw_footage/universal_kVpNwAmEosc_1080p.mp4"},
        "preferred_vault": "universal",
        "keywords": {"en": ["hyena hunting pack"]},
    }
    yt_info = resolve_scene_source_info(yt_scene)
    assert yt_info["platform"] == "YouTube"
    assert yt_info["video_id"] == "kVpNwAmEosc"
    assert yt_info["url"] == "https://www.youtube.com/watch?v=kVpNwAmEosc"
    assert yt_info["raw_filename"] == "universal_kVpNwAmEosc_1080p.mp4"
    assert yt_info["query"] == "hyena hunting pack"

    # 2. Douyin footage
    dy_scene = {
        "metadata": {"raw_asset_path": "cache/raw_footage/douyin_7198234123456.mp4"},
        "preferred_vault": "douyin",
    }
    dy_info = resolve_scene_source_info(dy_scene)
    assert dy_info["platform"] == "Douyin"
    assert dy_info["video_id"] == "7198234123456"
    assert dy_info["url"] == "https://www.douyin.com/video/7198234123456"

    # 3. Bilibili footage
    bili_scene = {
        "metadata": {"raw_asset_path": "cache/raw_footage/bilibili_BV1xx411c7mD.mp4"},
        "preferred_vault": "bilibili",
    }
    bili_info = resolve_scene_source_info(bili_scene)
    assert bili_info["platform"] == "Bilibili"
    assert bili_info["video_id"] == "BV1xx411c7mD"
    assert bili_info["url"] == "https://www.bilibili.com/video/BV1xx411c7mD"

    # 4. ProjectState to_dict populates source_info
    ps = ProjectState(
        project_id="test_proj",
        topic="Linh cẩu",
        skill_id="nature-wildlife-survival",
        target_duration_min=5,
        completed_scenes=[
            CompletedSceneRecord(
                scene_id="SCENE_001",
                chapter_index=1,
                text="Mở đầu phim.",
                duration_sec=5.0,
                word_count=10,
                word_budget_status="optimal",
                video_path="/path/to/scene_001.mp4",
                audio_path="/path/to/scene_001.wav",
                status="completed",
                preferred_vault="universal",
                metadata={"raw_asset_path": "cache/raw_footage/universal_2RI72hEvZug.mp4"},
            )
        ],
    )
    d = ps.to_dict()
    sc0 = d["completed_scenes"][0]
    assert "source_info" in sc0
    assert sc0["source_info"]["platform"] == "YouTube"
    assert sc0["source_info"]["url"] == "https://www.youtube.com/watch?v=2RI72hEvZug"






