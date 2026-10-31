"""
FastAPI Server & Studio Dashboard REST/SSE API (WU-08, REQ-PUB-02, VAC-UI-01, VAC-UI-02, VAC-UI-03, VAC-UI-04).
Provides:
- GET /: Visual Studio Dashboard UI
- POST /api/projects/create: 1-Click Wizard initialization
- POST /api/projects/{id}/start: Full-auto background pipeline execution
- GET /api/projects/{id}/status: Real-time progress state
- GET /api/projects/{id}/events: Server-Sent Events (SSE) streaming
- GET /api/projects/{id}/preview/scene/{scene_id}: Atomic scene preview player
- GET /api/projects/{id}/preview/video: Final 1080p video player
- GET /api/projects/{id}/preview/thumbnail: Diagnostic Safe-Zone thumbnail preview
- GET /api/projects/{id}/seo: SEO package & description
- POST /api/projects/{id}/publish: 1-Click YouTube Data API v3 publishing
- GET /api/system/health: Resource monitor (CPU, RAM, Rolling Buffer, Binaries)
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import shutil
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from autovideo.coordinator import MasterPipelineCoordinator, PipelineEvent, PipelineStage, ProjectState
from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.core.settings import SettingsManager
from autovideo.publisher.manager import PublishResult
from autovideo.skills.registry import SkillRegistry
from autovideo.ui import HTML_INDEX_PATH

logger = logging.getLogger(__name__)


# --- Pydantic Request Models ---

class CreateProjectRequest(BaseModel):
    """Payload for Quick Launch Wizard."""
    topic: str = Field(..., description="Project topic or investigation subject")
    skill_id: str = Field("nature-wildlife-survival", description="Skill niche identifier")
    target_duration_min: int = Field(15, ge=1, le=120, description="Target duration in minutes")
    project_id: Optional[str] = Field(None, description="Optional custom project identifier")


class PublishRequest(BaseModel):
    """Payload for 1-Click YouTube Publishing."""
    privacy_status: str = Field("private", description="YouTube video privacy status: private, unlisted, public")


class SaveSettingsRequest(BaseModel):
    """Payload for updating user & system configurations."""
    ninerouter_api_key: Optional[str] = Field(None, description="9router API key")
    ninerouter_base_url: Optional[str] = Field(None, description="9router base URL (e.g. http://localhost:20128/v1)")
    llm_provider: Optional[str] = Field(None, description="Active LLM provider: 9router or gemini")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API key")
    llm_model: Optional[str] = Field(None, description="Selected LLM model (e.g. antigravity/claude-3-5-sonnet, codex/gpt-4o)")
    cached_models: Optional[List[str]] = Field(None, description="Cached list of models from 9router")
    
    # Thumbnail & Image Generation
    image_provider: Optional[str] = Field(None, description="Image generation provider: 9router or none")
    image_model: Optional[str] = Field(None, description="Image generation model (e.g. ag/gemini-3.8-flash)")
    
    # TTS Providers
    tts_primary_provider: Optional[str] = Field(None, description="Primary TTS engine: zerotts, maziao, edge_tts")
    tts_enable_fallback: Optional[bool] = Field(None, description="Whether to fall back to secondary TTS engine")
    zerotts_voice: Optional[str] = Field(None, description="ZeroTTS voice: banmai, maichi, minhquang, thientam")
    zerotts_comma_pause_ms: Optional[int] = Field(None, ge=50, le=1000, description="ZeroTTS comma pause ms")
    zerotts_period_pause_ms: Optional[int] = Field(None, ge=100, le=2000, description="ZeroTTS period pause ms")
    maziao_api_key: Optional[str] = Field(None, description="Maziao Cloud TTS API key")
    maziao_base_url: Optional[str] = Field(None, description="Maziao Cloud TTS base URL")
    maziao_model_id: Optional[str] = Field(None, description="Maziao Model ID")
    maziao_voice_id: Optional[str] = Field(None, description="Maziao Voice ID")
    maziao_volume: Optional[float] = Field(None, ge=0.1, le=2.0, description="Maziao volume")
    maziao_pitch: Optional[float] = Field(None, ge=0.1, le=2.0, description="Maziao pitch")
    edge_tts_voice: Optional[str] = Field(None, description="Edge-TTS voice identifier")

    douyin_cookie: Optional[str] = Field(None, description="Raw Douyin cookie string")
    jitter_min_sec: Optional[float] = Field(None, ge=0.5, le=10.0, description="Min jitter delay")
    jitter_max_sec: Optional[float] = Field(None, ge=1.0, le=20.0, description="Max jitter delay")
    default_voice: Optional[str] = Field(None, description="Default TTS voice")
    speech_rate: Optional[float] = Field(None, ge=0.5, le=2.0, description="TTS speech speed multiplier")
    target_lufs: Optional[float] = Field(None, ge=-30.0, le=-6.0, description="Audio normalization target LUFS")
    rolling_buffer_max_gb: Optional[float] = Field(None, ge=1.0, le=50.0, description="Max rolling buffer limit in GB")
    render_concurrency: Optional[int] = Field(None, ge=1, le=8, description="Render concurrency threads")
    clean_intermediate_parts: Optional[bool] = Field(None, description="Auto-clean intermediate chapter parts")


class TestGeminiRequest(BaseModel):
    """Payload for testing Gemini API key connectivity."""
    api_key: Optional[str] = Field(None, description="Gemini API key to test")


class TestMaziaoRequest(BaseModel):
    """Payload for testing Maziao TTS API key connectivity."""
    api_key: Optional[str] = Field(None, description="Maziao API key to test")
    base_url: Optional[str] = Field(None, description="Maziao base URL")


class NineRouterModelsRequest(BaseModel):
    """Payload for fetching or testing 9router models."""
    base_url: Optional[str] = Field(None, description="9router base URL")
    api_key: Optional[str] = Field(None, description="9router API key")


# --- System Resource Probing Helper ---

def get_system_health(config: AppConfig, binary_manager: BinaryManager) -> Dict[str, Any]:
    """Inspects host resources and external binary availability."""
    # 1. RAM Usage
    ram_used_pct = 0
    ram_total_gb = 0.0
    if sys.platform == "win32":
        try:
            from ctypes import wintypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', wintypes.DWORD),
                    ('dwMemoryLoad', wintypes.DWORD),
                    ('ullTotalPhys', wintypes.ULARGE_INTEGER),
                    ('ullAvailPhys', wintypes.ULARGE_INTEGER),
                    ('ullTotalPageFile', wintypes.ULARGE_INTEGER),
                    ('ullAvailPageFile', wintypes.ULARGE_INTEGER),
                    ('ullTotalVirtual', wintypes.ULARGE_INTEGER),
                    ('ullAvailVirtual', wintypes.ULARGE_INTEGER),
                    ('ullAvailExtendedVirtual', wintypes.ULARGE_INTEGER),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_used_pct = int(stat.dwMemoryLoad)
            ram_total_gb = round(stat.ullTotalPhys / (1024**3), 1)
        except Exception:
            ram_used_pct = 50
    else:
        ram_used_pct = 50

    # 2. Disk and Rolling Buffer
    cache_path = config.paths.cache_dir
    cache_path.mkdir(parents=True, exist_ok=True)
    try:
        disk_usage = shutil.disk_usage(str(cache_path))
        disk_free_gb = round(disk_usage.free / (1024**3), 2)
        disk_total_gb = round(disk_usage.total / (1024**3), 2)
    except Exception:
        disk_free_gb = 100.0
        disk_total_gb = 500.0

    # Calculate rolling buffer total size
    buffer_bytes = 0
    if config.paths.cache_temp_scenes_dir.exists():
        for f in config.paths.cache_temp_scenes_dir.rglob("*"):
            if f.is_file():
                buffer_bytes += f.stat().st_size
    buffer_gb = round(buffer_bytes / (1024**3), 2)

    # 3. Binaries status
    binary_statuses = binary_manager.check_all()

    # 4. CPU count and estimation
    cpu_cores = os.cpu_count() or 4
    # Approximate CPU load
    cpu_load_pct = min(100, max(5, int(ram_used_pct * 0.4)))

    return {
        "status": "healthy",
        "cpu_cores": cpu_cores,
        "cpu_load_pct": cpu_load_pct,
        "ram_used_pct": ram_used_pct,
        "ram_total_gb": ram_total_gb,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "rolling_buffer_gb": buffer_gb,
        "rolling_buffer_limit_gb": getattr(config.performance, "rolling_buffer_max_gb", 5.0),
        "binaries": {k: v.to_dict() for k, v in binary_statuses.items()},
        "zerotts_ready": True,
    }


# --- App Factory ---

def create_app(
    config: Optional[AppConfig] = None,
    coordinator: Optional[MasterPipelineCoordinator] = None,
) -> FastAPI:
    """Factory creating configured FastAPI app instance."""
    app_config = config or get_config()
    binary_mgr = BinaryManager(config=app_config)
    coord = coordinator or MasterPipelineCoordinator(
        config=app_config, binary_manager=binary_mgr
    )
    settings_mgr = SettingsManager(config=app_config)
    skill_registry = SkillRegistry()

    api = FastAPI(
        title="BanContentAuto Studio Dashboard",
        description="Unified Desktop Production GUI and Automated Video Pipeline Orchestrator",
        version="2.0.0",
    )

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State injection
    api.state.config = app_config
    api.state.binary_manager = binary_mgr
    api.state.coordinator = coord
    api.state.settings_manager = settings_mgr
    api.state.skill_registry = skill_registry

    # --- Endpoints ---

    @api.get("/api/skills")
    async def list_skills_endpoint() -> Dict[str, Any]:
        """Lists all installed Skill Niches and their metadata."""
        skills = skill_registry.list_skills()
        return {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "style_name": s.style_name,
                    "badge": s.badge,
                    "version": s.manifest.version,
                    "description": s.description,
                    "languages": s.manifest.languages,
                }
                for s in skills
            ],
            "total": len(skills),
        }

    @api.get("/", response_class=HTMLResponse)
    async def serve_dashboard() -> HTMLResponse:
        """Serves the main Studio Dashboard visual interface."""
        if HTML_INDEX_PATH.exists():
            return HTMLResponse(content=HTML_INDEX_PATH.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>BanContentAuto Studio Dashboard</h1><p>UI template not found.</p>"
        )

    @api.get("/api/system/health")
    async def system_health() -> Dict[str, Any]:
        """Provides CPU, RAM, disk buffer, and external binary statuses."""
        return get_system_health(api.state.config, api.state.binary_manager)

    @api.get("/api/system/settings")
    async def get_system_settings_endpoint() -> Dict[str, Any]:
        """Provides masked system settings and cache diagnostics for Studio Settings GUI."""
        return api.state.settings_manager.get_masked_settings()

    @api.post("/api/system/settings")
    async def save_system_settings_endpoint(req: SaveSettingsRequest) -> Dict[str, Any]:
        """Updates and persists user settings to config/settings.json."""
        api.state.settings_manager.save_settings(req.model_dump(exclude_unset=True))
        return {
            "success": True,
            "message": "Cấu hình hệ thống đã được lưu thành công",
            "settings": api.state.settings_manager.get_masked_settings(),
        }

    @api.post("/api/system/settings/test-gemini")
    async def test_gemini_endpoint(req: TestGeminiRequest) -> Dict[str, Any]:
        """Validates Google Gemini API key connectivity."""
        success, message = api.state.settings_manager.test_gemini_api(api_key=req.api_key)
        return {"success": success, "message": message}

    @api.post("/api/system/settings/9router/test")
    async def test_ninerouter_endpoint(req: NineRouterModelsRequest) -> Dict[str, Any]:
        """Validates 9router connection and returns status."""
        success, message, models = api.state.settings_manager.fetch_ninerouter_models(
            base_url=req.base_url, api_key=req.api_key
        )
        return {"success": success, "message": message, "count": len(models)}

    @api.post("/api/system/settings/9router/models")
    async def get_ninerouter_models_endpoint(req: NineRouterModelsRequest) -> Dict[str, Any]:
        """Retrieves real-time model list from 9router gateway."""
        success, message, models = api.state.settings_manager.fetch_ninerouter_models(
            base_url=req.base_url, api_key=req.api_key
        )
        return {"success": success, "message": message, "models": models}

    @api.post("/api/system/settings/test-maziao")
    async def test_maziao_endpoint(req: TestMaziaoRequest) -> Dict[str, Any]:
        """Validates Maziao TTS API key connectivity."""
        success, message = api.state.settings_manager.test_maziao_api(api_key=req.api_key, base_url=req.base_url)
        return {"success": success, "message": message}

    @api.get("/api/system/tts/zerotts/voices")
    async def get_zerotts_voices_endpoint() -> Dict[str, Any]:
        """Lists official and user-installed cloned ZeroTTS voices."""
        voices = api.state.settings_manager.get_zerotts_voices()
        return {"success": True, "count": len(voices), "voices": voices}

    @api.post("/api/system/tts/zerotts/install-clone")
    async def install_zerotts_clone_endpoint(file: UploadFile = File(...)) -> Dict[str, Any]:
        """Installs a ZeroTTS voice pack (.zip or .npz) from upload."""
        contents = await file.read()
        success, message, voice_info = api.state.settings_manager.install_zerotts_clone_voice(
            file_bytes=contents, file_name=file.filename or "cloned_voice.zip"
        )
        return {"success": success, "message": message, "voice": voice_info}

    @api.post("/api/system/settings/maziao/voices")
    async def get_maziao_voices_endpoint(req: TestMaziaoRequest) -> Dict[str, Any]:
        """Fetches dynamic voice list from Maziao Cloud (system + user cloned)."""
        success, message, voices = api.state.settings_manager.fetch_maziao_voices(
            api_key=req.api_key, base_url=req.base_url
        )
        return {"success": success, "message": message, "count": len(voices), "voices": voices}

    @api.post("/api/system/binaries/setup")
    async def setup_binaries_endpoint() -> Dict[str, Any]:
        """Automatically installs or copies missing external binaries into bin/."""
        result = api.state.settings_manager.setup_binaries()
        return result

    @api.post("/api/system/cache/clear")
    async def clear_system_cache_endpoint() -> Dict[str, Any]:
        """Cleans intermediate temporary files in cache/ subdirectories."""
        result = api.state.settings_manager.clear_cache()
        return result

    @api.get("/api/projects")
    async def list_projects_endpoint() -> Dict[str, Any]:
        """Lists all registered projects, their statuses, progress, and video assets."""
        projects = coord.list_projects()
        return {"projects": projects, "total": len(projects)}

    @api.get("/api/projects/queue")
    async def get_projects_queue_endpoint() -> Dict[str, Any]:
        """Provides status of the active project and current queue backlog."""
        return coord.get_queue_info()

    @api.post("/api/projects/create")
    async def create_project(req: CreateProjectRequest) -> Dict[str, Any]:
        """Initializes a new project via 1-Click Wizard (VAC-UI-01)."""
        project = coord.get_or_create_project(
            topic=req.topic,
            skill_id=req.skill_id,
            target_duration_min=req.target_duration_min,
            project_id=req.project_id,
        )
        return project.to_dict()

    @api.post("/api/projects/{project_id}/start")
    async def start_pipeline(project_id: str) -> Dict[str, Any]:
        """Enqueues or immediately executes the automated 4-step pipeline."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        result = coord.enqueue_project(project_id=project_id, resume=True)
        return result

    @api.post("/api/projects/{project_id}/stop")
    async def stop_pipeline(project_id: str) -> Dict[str, Any]:
        """Stops or cancels a running or queued project execution."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        success = coord.cancel_project(project_id=project_id)
        return {
            "success": success,
            "project_id": project_id,
            "stage": project.stage.value,
            "message": "Đã yêu cầu dừng sản xuất dự án" if success else "Không thể dừng dự án",
        }

    @api.delete("/api/projects/{project_id}")
    async def delete_project_endpoint(project_id: str) -> Dict[str, Any]:
        """Deletes a project record and frees associated disk files."""
        success = coord.delete_project(project_id=project_id)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"success": True, "status": "deleted", "project_id": project_id, "message": f"Dự án {project_id} đã được xóa thành công."}

    @api.get("/api/projects/{project_id}/status")
    async def get_project_status(project_id: str) -> Dict[str, Any]:
        """Returns the full real-time state of the project (VAC-UI-02)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.to_dict()

    @api.get("/api/projects/{project_id}/events")
    async def stream_project_events(project_id: str) -> StreamingResponse:
        """Server-Sent Events (SSE) stream for live GUI monitoring."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        queue = coord.subscribe_events(project_id)

        async def event_generator():
            try:
                while True:
                    event: PipelineEvent = await queue.get()
                    yield event.to_sse_payload()
                    if event.stage in (
                        PipelineStage.COMPLETE,
                        PipelineStage.ERROR,
                        PipelineStage.CANCELLED,
                    ):
                        break
            except asyncio.CancelledError:
                pass
            finally:
                coord.unsubscribe_events(project_id, queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @api.get("/api/projects/{project_id}/preview/scene/{scene_id}")
    async def preview_scene(project_id: str, scene_id: str) -> FileResponse:
        """Streams atomic scene MP4 for the Mini Video Player (VAC-UI-03)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        matching_scene = next(
            (s for s in project.completed_scenes if s.scene_id == scene_id),
            None,
        )
        if not matching_scene or not matching_scene.video_path:
            raise HTTPException(status_code=404, detail="Scene video not found")

        scene_file = Path(matching_scene.video_path)
        if not scene_file.exists():
            raise HTTPException(status_code=404, detail="Scene video file missing on disk")

        return FileResponse(scene_file, media_type="video/mp4")

    @api.get("/api/projects/{project_id}/preview/video")
    async def preview_final_video(project_id: str) -> FileResponse:
        """Streams final 1080p MP4 video for the Publishing Hub (VAC-UI-04)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.final_video_path:
            raise HTTPException(status_code=404, detail="Final video has not been rendered yet")

        video_file = Path(project.final_video_path)
        if not video_file.exists():
            raise HTTPException(status_code=404, detail="Video file missing on disk")

        return FileResponse(video_file, media_type="video/mp4")

    @api.get("/api/projects/{project_id}/preview/thumbnail")
    async def preview_thumbnail(project_id: str) -> FileResponse:
        """Returns counterpoint thumbnail with safe-zone overlay (VAC-UI-04)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Prefer safe-zone overlay preview if generated
        thumb_path = (
            Path(project.thumbnail_preview_path)
            if project.thumbnail_preview_path
            else (Path(project.thumbnail_path) if project.thumbnail_path else None)
        )

        if not thumb_path or not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail preview not found")

        return FileResponse(thumb_path, media_type="image/jpeg")

    @api.get("/api/projects/{project_id}/preview/thumbnail/raw")
    async def preview_raw_thumbnail(project_id: str) -> FileResponse:
        """Returns the raw AI-generated base image (before text/badge compositing)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        p_dir = config.paths.get_project_render_dir(project_id)
        raw_path = p_dir / "thumbnail_raw.jpg"
        if not raw_path.exists():
            raw_path = p_dir / "thumbnail.jpg"
        if not raw_path.exists():
            raise HTTPException(status_code=404, detail="Raw thumbnail not available")
        return FileResponse(raw_path, media_type="image/jpeg")

    class RegenerateThumbnailRequest(BaseModel):
        prompt: Optional[str] = None
        hook: Optional[str] = None
        badge: Optional[str] = None
        model: Optional[str] = None

    @api.post("/api/projects/{project_id}/thumbnail/regenerate")
    async def regenerate_thumbnail(
        project_id: str,
        req: Optional[RegenerateThumbnailRequest] = None,
    ) -> Dict[str, Any]:
        """Regenerates AI thumbnail using 9Router and composites with safe zone overlay."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        p_dir = config.paths.get_project_render_dir(project_id)
        p_dir.mkdir(parents=True, exist_ok=True)
        raw_path = p_dir / "thumbnail_raw.jpg"
        thumb_path = p_dir / "thumbnail.jpg"
        preview_path = p_dir / "thumbnail_safe_zone_preview.jpg"

        seo = project.seo_package or {}
        topic = project.topic or "Video"
        prompt_to_use = (req.prompt if req and req.prompt else None) or seo.get("thumbnail_prompt") or (
            f"Dramatic photorealistic documentary thumbnail of {topic}, cinematic 8k lighting, empty bottom-right safe zone"
        )
        hook_to_use = (req.hook if req and req.hook else None) or seo.get("thumbnail_hook") or "TIÊU ĐIỂM"
        badge_to_use = (req.badge if req and req.badge else None) or seo.get("thumbnail_badge") or "KHÁM PHÁ"

        from autovideo.core.settings import SettingsManager
        from autovideo.publisher.image_client import NineRouterImageClient
        from autovideo.publisher.thumbnail_generator import ThumbnailGenerator

        sm = SettingsManager(config=config)
        stg = sm.get_settings()
        model_to_use = (req.model if req and req.model else None) or getattr(stg, "image_model", "ag/gemini-3.8-flash")

        img_client = NineRouterImageClient()
        img_client.generate_image(
            prompt=prompt_to_use,
            output_path=raw_path,
            model=model_to_use,
        )

        thumb_gen = ThumbnailGenerator()
        thumb_gen.generate(
            hook_text=hook_to_use,
            tension_badge=badge_to_use,
            base_image=raw_path,
            output_path=thumb_path,
            strict_counterpoint=False,
        )
        thumb_gen.render_safe_zone_overlay(
            image_or_path=thumb_path,
            output_path=preview_path,
        )

        project.thumbnail_path = str(thumb_path)
        project.thumbnail_preview_path = str(preview_path)

        now_ts = int(time.time())
        return {
            "status": "ok",
            "message": "Ảnh Thumbnail AI đã được tạo mới thành công!",
            "thumbnail_url": f"/api/projects/{project_id}/preview/thumbnail?t={now_ts}",
            "thumbnail_raw_url": f"/api/projects/{project_id}/preview/thumbnail/raw?t={now_ts}",
        }

    @api.get("/api/projects/{project_id}/seo")
    async def get_seo_package(project_id: str) -> Dict[str, Any]:
        """Returns YouTube SEO package metadata and timestamps."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.seo_package:
            raise HTTPException(status_code=404, detail="SEO package not generated yet")

        return project.seo_package

    @api.post("/api/projects/{project_id}/publish")
    async def publish_to_youtube(project_id: str, req: PublishRequest) -> Dict[str, Any]:
        """1-Click YouTube publication via Data API v3 (REQ-B4-02)."""
        project = coord.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.final_video_path or not Path(project.final_video_path).exists():
            raise HTTPException(status_code=400, detail="Final video not ready for publishing")

        try:
            # Reconstruct PublishResult for YouTube upload
            pub_result = PublishResult(
                project_id=project_id,
                output_dir=api.state.config.paths.get_project_render_dir(project_id),
                thumbnail_path=Path(project.thumbnail_path) if project.thumbnail_path else Path(""),
                thumbnail_preview_path=Path(project.thumbnail_preview_path) if project.thumbnail_preview_path else Path(""),
                seo_markdown_path=Path(project.seo_markdown_path) if project.seo_markdown_path else Path(""),
                seo_package=None,  # Handled inside publisher manager or mock
                video_path=Path(project.final_video_path),
            )

            # Publish using publisher manager uploader
            upload_status = coord.publisher_manager.publish_to_youtube(
                publish_result=pub_result,
                privacy_status=req.privacy_status,
            )

            is_success = upload_status.status == "completed"
            return {
                "success": is_success,
                "video_id": upload_status.video_id,
                "video_url": upload_status.video_url,
                "error": upload_status.error_message,
            }
        except Exception as e:
            logger.exception("Failed to publish to YouTube: %s", e)
            return {"success": False, "error": str(e)}

    return api


# Default application instance for uvicorn
app = create_app()


def find_free_port(host: str, starting_port: int, max_attempts: int = 20) -> int:
    """Find a free TCP port starting from starting_port."""
    import socket
    for port in range(starting_port, starting_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return starting_port


def main() -> None:
    """CLI launcher for BanContentAuto Studio Dashboard."""
    import uvicorn

    parser = argparse.ArgumentParser(description="BanContentAuto Studio Dashboard Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (automatically picks next available if busy)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open browser on start")
    args = parser.parse_args()

    actual_port = find_free_port(args.host, args.port)
    if actual_port != args.port:
        print(f"[!] Cong {args.port} dang duoc tien trinh khac su dung. Tu dong chuyen sang cong trong: {actual_port}")

    url = f"http://{args.host}:{actual_port}"
    print(f"\n========================================================")
    print(f"  BANCONTENT AUTO STUDIO DASHBOARD [v2.0]")
    print(f"  Live at: {url}")
    print(f"========================================================\n")

    if args.open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=actual_port, log_level="info")


if __name__ == "__main__":
    main()
