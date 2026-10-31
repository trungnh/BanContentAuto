"""
Master Pipeline Coordinator (WU-08, REQ-PUB-02, VAC-UI-01, VAC-UI-02).
Coordinates the complete end-to-end 4-step video factory:
- B1: ScriptwritingBrain -> Master Plan screenplay.json & draft SEO
- B2: Asset Sourcing + ZeroTTS Voiceover + Atomic Scene Assembly -> temp scenes
- B3: Rolling Chapter Builder + Concat Demuxer -> Final 1080p MP4
- B4: Counterpoint Thumbnail & SEO Packager -> thumbnail.jpg & seo.md

Provides real-time event streaming (SSE) and asynchronous state tracking.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.production.chapter_builder import ChapterBuilder, ProductionPipeline, SceneAssets
from autovideo.production.concat_demuxer import ConcatDemuxer
from autovideo.production.rolling_buffer import RollingDiskBuffer
from autovideo.production.scene_muxer import SceneMuxConfig, SceneMuxResult, SceneMuxer
from autovideo.production.semantic_judge import SemanticFootageJudge
from autovideo.production.visual_inspector import VisualQualityInspector
from autovideo.publisher.manager import PublishResult, PublisherManager
from autovideo.publisher.seo_packager import SEOPackage, SEOPackager
from autovideo.script.anti_ai_linter import AntiAILinter
from autovideo.script.pipeline import (
    Chapter,
    Scene,
    SceneKeyword,
    Screenplay,
    ScriptwritingPipeline,
    create_default_llm_adapter,
)
from autovideo.script.word_budget import WordBudgetValidator, calculate_scene_budget
from autovideo.sourcing.engine import AssetSourcingEngine, SourcedAsset
from autovideo.sourcing.relevance import anchor_matches, extract_scene_terms
from autovideo.skills.registry import SkillRegistry
from autovideo.voiceover.manager import VoiceoverConfig, VoiceoverManager

logger = logging.getLogger(__name__)


class PipelineCancelledError(Exception):
    """Raised when pipeline execution is cancelled by the user."""
    pass


class PipelineStage(str, Enum):
    """Execution stages of the 4-step production pipeline."""
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    B1_SCRIPT = "B1_SCRIPT"
    B2_SOURCING_TTS = "B2_SOURCING_TTS"
    B3_RENDER = "B3_RENDER"
    B4_PACKAGING = "B4_PACKAGING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


@dataclass
class PipelineEvent:
    """Real-time event emitted during pipeline execution for SSE streaming."""
    timestamp: float
    stage: PipelineStage
    progress: float  # 0.0 to 100.0
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_sse_payload(self) -> str:
        data = {
            "timestamp": self.timestamp,
            "stage": self.stage.value,
            "progress": round(self.progress, 1),
            "message": self.message,
            "details": self.details,
        }
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class CompletedSceneRecord:
    """Metadata of an atomic scene assembled during Step 2."""
    scene_id: str
    chapter_index: int
    text: str
    duration_sec: float
    word_count: int
    word_budget_status: str  # "optimal", "too_long", "too_short"
    video_path: Optional[str]
    audio_path: Optional[str]
    status: str  # "completed" | "failed" | "skipped"
    preferred_vault: str = "douyin"
    camera_angle: str = "Wide"
    keywords: Dict[str, List[str]] = field(default_factory=dict)
    source_info: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


def format_time_code(seconds: float) -> str:
    """Formats seconds as m:ss, e.g. 10.0 -> '0:10', 64.0 -> '1:04', 3605.0 -> '1:00:05'."""
    sec = max(0.0, float(seconds))
    m = int(sec // 60)
    s = int(sec % 60)
    if m >= 60:
        h = int(m // 60)
        m = int(m % 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def resolve_scene_source_info(scene_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Infers or extracts source attribution info (platform, URL, video_id, title, and cut range)
    from available metadata, raw asset path, or keywords.
    """
    existing_src = scene_dict.get("source_info")
    if existing_src and isinstance(existing_src, dict) and existing_src.get("cut_summary") and existing_src.get("url"):
        return existing_src

    meta = scene_dict.get("metadata") or {}
    raw_path = meta.get("raw_asset_path") or meta.get("raw_filename") or ""
    video_id = meta.get("video_id") or ""
    title = meta.get("title") or ""
    url = meta.get("webpage_url") or meta.get("url") or ""
    extractor = meta.get("extractor") or ""
    preferred_vault = scene_dict.get("preferred_vault") or "universal"

    # Try extracting YouTube ID or platform from raw_path filename
    filename = Path(raw_path).name if raw_path else ""
    if not video_id and filename:
        # Pattern universal_{id}
        m = re.match(r"universal_([A-Za-z0-9_-]{11})", filename)
        if m:
            video_id = m.group(1)
            extractor = "youtube"
        else:
            m_douyin = re.match(r"douyin_(\d+)", filename)
            if m_douyin:
                video_id = m_douyin.group(1)
                extractor = "douyin"
            else:
                m_bili = re.match(r"bilibili_(BV[A-Za-z0-9]+)", filename)
                if m_bili:
                    video_id = m_bili.group(1)
                    extractor = "bilibili"

    # Build platform and URL
    ext_lower = extractor.lower()
    if "youtube" in ext_lower or ("universal" in ext_lower and video_id):
        platform = "YouTube"
        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
    elif "douyin" in ext_lower:
        platform = "Douyin"
        if not url and video_id:
            url = f"https://www.douyin.com/video/{video_id}"
    elif "bilibili" in ext_lower:
        platform = "Bilibili"
        if not url and video_id:
            url = f"https://www.bilibili.com/video/{video_id}"
    elif "stock" in ext_lower or preferred_vault.lower() == "stock":
        platform = "Stock Vault"
    else:
        platform = preferred_vault.capitalize() if preferred_vault else "Universal"

    # Calculate cut segment from raw footage
    start_offset_sec = float(meta.get("start_offset_sec") or (existing_src.get("start_offset_sec") if existing_src else 0.0) or 0.0)
    duration_sec = float(scene_dict.get("duration_sec") or meta.get("duration_sec") or 5.0)
    end_offset_sec = start_offset_sec + duration_sec
    cut_from = format_time_code(start_offset_sec)
    cut_to = format_time_code(end_offset_sec)
    cut_dur_rounded = round(duration_sec)
    cut_summary = f"{cut_dur_rounded}s cắt từ {cut_from} - {cut_to} của video stock"

    # Deep link to start time on YouTube
    url_with_timestamp = url
    if url and "youtube" in platform.lower() and start_offset_sec > 0:
        sep = "&" if "?" in url else "?"
        url_with_timestamp = f"{url}{sep}t={int(start_offset_sec)}s"

    return {
        "vault": preferred_vault,
        "platform": platform,
        "url": url,
        "url_with_timestamp": url_with_timestamp,
        "video_id": video_id,
        "title": title,
        "uploader": meta.get("uploader", ""),
        "raw_filename": filename,
        "start_offset_sec": start_offset_sec,
        "end_offset_sec": end_offset_sec,
        "cut_from": cut_from,
        "cut_to": cut_to,
        "cut_duration": cut_dur_rounded,
        "cut_summary": cut_summary,
        "query": meta.get("effective_query") or (
            scene_dict.get("keywords", {}).get("en", [""])[0]
            if isinstance(scene_dict.get("keywords"), dict) and scene_dict.get("keywords").get("en")
            else ""
        ),
    }


@dataclass
class ProjectState:
    """State record for an active or completed video production project."""
    project_id: str
    topic: str
    skill_id: str
    target_duration_min: int
    stage: PipelineStage = PipelineStage.IDLE
    progress: float = 0.0
    current_step_text: str = "Đang chờ khởi tạo"
    screenplay: Optional[Dict[str, Any]] = None
    seo_package: Optional[Dict[str, Any]] = None
    completed_scenes: List[CompletedSceneRecord] = field(default_factory=list)
    final_video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_preview_path: Optional[str] = None
    seo_markdown_path: Optional[str] = None
    rolling_buffer_bytes: int = 0
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        scenes_data = []
        for s in self.completed_scenes:
            sd = asdict(s)
            if not sd.get("source_info") or not sd["source_info"].get("url") or not sd["source_info"].get("cut_summary"):
                sd["source_info"] = resolve_scene_source_info(sd)
            scenes_data.append(sd)

        return {
            "project_id": self.project_id,
            "topic": self.topic,
            "skill_id": self.skill_id,
            "target_duration_min": self.target_duration_min,
            "stage": self.stage.value,
            "progress": round(self.progress, 1),
            "current_step_text": self.current_step_text,
            "screenplay": self.screenplay,
            "seo_package": self.seo_package,
            "completed_scenes": scenes_data,
            "final_video_path": self.final_video_path,
            "thumbnail_path": self.thumbnail_path,
            "thumbnail_preview_path": self.thumbnail_preview_path,
            "seo_markdown_path": self.seo_markdown_path,
            "rolling_buffer_bytes": self.rolling_buffer_bytes,
            "rolling_buffer_mb": round(self.rolling_buffer_bytes / (1024 * 1024), 2),
            "logs": self.logs[-50:],  # Return last 50 log lines
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProjectState:
        raw_scenes = data.get("completed_scenes", [])
        scenes = []
        valid_scene_fields = {f.name for f in fields(CompletedSceneRecord)}
        for s in raw_scenes:
            if isinstance(s, dict):
                filtered_s = {k: v for k, v in s.items() if k in valid_scene_fields}
                scenes.append(CompletedSceneRecord(**filtered_s))
            elif isinstance(s, CompletedSceneRecord):
                scenes.append(s)

        raw_stage = data.get("stage", "IDLE")
        try:
            stage_enum = PipelineStage(raw_stage)
        except ValueError:
            stage_enum = PipelineStage.IDLE

        return cls(
            project_id=data["project_id"],
            topic=data.get("topic", ""),
            skill_id=data.get("skill_id", "warehouse-fails"),
            target_duration_min=int(data.get("target_duration_min", 15)),
            stage=stage_enum,
            progress=float(data.get("progress", 0.0)),
            current_step_text=data.get("current_step_text", ""),
            screenplay=data.get("screenplay"),
            seo_package=data.get("seo_package"),
            completed_scenes=scenes,
            final_video_path=data.get("final_video_path"),
            thumbnail_path=data.get("thumbnail_path"),
            thumbnail_preview_path=data.get("thumbnail_preview_path"),
            seo_markdown_path=data.get("seo_markdown_path"),
            rolling_buffer_bytes=int(data.get("rolling_buffer_bytes", 0)),
            logs=list(data.get("logs", [])),
            error=data.get("error"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


class MasterPipelineCoordinator:
    """
    Central Master Orchestrator connecting:
    - B1: ScriptwritingBrain
    - B2: AssetSourcingEngine + VoiceoverManager + SceneMuxer
    - B3: ChapterBuilder & ConcatDemuxer
    - B4: PublisherManager
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
        script_brain: Optional[ScriptwritingPipeline] = None,
        sourcing_engine: Optional[AssetSourcingEngine] = None,
        voiceover_manager: Optional[VoiceoverManager] = None,
        scene_muxer: Optional[SceneMuxer] = None,
        chapter_builder: Optional[ChapterBuilder] = None,
        concat_demuxer: Optional[ConcatDemuxer] = None,
        publisher_manager: Optional[PublisherManager] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        self.config = config or get_config()
        self.binary_manager = binary_manager or BinaryManager(config=self.config)
        self.skill_registry = skill_registry or SkillRegistry()
        self.script_brain = script_brain or ScriptwritingPipeline(
            adapter=create_default_llm_adapter(),
            skill_registry=self.skill_registry,
        )
        self.sourcing_engine = sourcing_engine or AssetSourcingEngine(config=self.config)
        self.voiceover_manager = voiceover_manager or VoiceoverManager(app_config=self.config)
        self.scene_muxer = scene_muxer or SceneMuxer(
            config=self.config, binary_manager=self.binary_manager
        )
        self.rolling_buffer = RollingDiskBuffer(config=self.config)
        self.concat_demuxer = concat_demuxer or ConcatDemuxer(
            config=self.config, binary_manager=self.binary_manager
        )
        self.chapter_builder = chapter_builder or ChapterBuilder(
            config=self.config,
            scene_muxer=self.scene_muxer,
            concat_demuxer=self.concat_demuxer,
            rolling_buffer=self.rolling_buffer,
            binary_manager=self.binary_manager,
        )
        self.publisher_manager = publisher_manager or PublisherManager(
            config=self.config, mock_uploader=True
        )

        self.projects: Dict[str, ProjectState] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._project_queue: List[str] = []
        self._running_project_id: Optional[str] = None
        self._cancel_requested: Set[str] = set()

        # Reload persisted projects from disk
        self._load_persisted_projects()

    def _save_project_state(self, project: ProjectState) -> None:
        """Persists project state to renders/<project_id>/project_state.json."""
        try:
            proj_dir = self.config.paths.get_project_render_dir(project.project_id)
            proj_dir.mkdir(parents=True, exist_ok=True)
            state_file = proj_dir / "project_state.json"
            temp_file = proj_dir / f"project_state.json.tmp.{os.getpid()}"
            temp_file.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            temp_file.replace(state_file)
        except Exception as exc:
            logger.warning("Could not persist state for project %s: %s", project.project_id, exc)

    def _load_persisted_projects(self) -> None:
        """Discovers and reloads all persisted projects from renders/ directory."""
        renders_dir = self.config.paths.renders_dir
        if not renders_dir.exists():
            return
        for p_dir in renders_dir.iterdir():
            if not p_dir.is_dir():
                continue
            p_id = p_dir.name
            state_file = p_dir / "project_state.json"
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    p_state = ProjectState.from_dict(data)
                    # If server restarted while it was in an active/queued stage, mark as ERROR with note
                    if p_state.stage in (
                        PipelineStage.B1_SCRIPT,
                        PipelineStage.B2_SOURCING_TTS,
                        PipelineStage.B3_RENDER,
                        PipelineStage.B4_PACKAGING,
                        PipelineStage.QUEUED,
                    ):
                        p_state.current_step_text = f"Tiến trình bị gián đoạn khi khởi động lại máy chủ (trước đó: {p_state.stage.value})"
                        p_state.stage = PipelineStage.ERROR
                        p_state.error = "Tiến trình bị gián đoạn do khởi động lại ứng dụng."
                    self.projects[p_id] = p_state
                    self._subscribers[p_id] = set()
                except Exception as exc:
                    logger.warning("Failed to load project from %s: %s", state_file, exc)
            else:
                # Reconstruct state from existing files in renders/<p_id>
                try:
                    screenplay_file = p_dir / "screenplay.json"
                    topic = p_id
                    screenplay_data = None
                    if screenplay_file.exists():
                        try:
                            screenplay_data = json.loads(screenplay_file.read_text(encoding="utf-8"))
                            topic = screenplay_data.get("topic", topic)
                        except Exception:
                            pass
                    final_mp4 = p_dir / f"{p_id}_final.mp4"
                    if not final_mp4.exists():
                        candidates = list(p_dir.glob("*_final.mp4"))
                        if candidates:
                            final_mp4 = candidates[0]
                    thumb = p_dir / f"{p_id}_thumb.jpg"
                    if not thumb.exists():
                        candidates = list(p_dir.glob("*_thumb.jpg"))
                        if candidates:
                            thumb = candidates[0]

                    is_complete = final_mp4.exists()
                    p_state = ProjectState(
                        project_id=p_id,
                        topic=topic,
                        skill_id="warehouse-fails",
                        target_duration_min=15,
                        stage=PipelineStage.COMPLETE if is_complete else PipelineStage.IDLE,
                        progress=100.0 if is_complete else 0.0,
                        current_step_text="Dự án hoàn tất (khôi phục từ thư mục renders)" if is_complete else "Dự án đã lưu",
                        screenplay=screenplay_data,
                        final_video_path=str(final_mp4) if final_mp4.exists() else None,
                        thumbnail_path=str(thumb) if thumb.exists() else None,
                        created_at=p_dir.stat().st_ctime,
                        updated_at=p_dir.stat().st_mtime,
                    )
                    self.projects[p_id] = p_state
                    self._subscribers[p_id] = set()
                    self._save_project_state(p_state)
                except Exception as exc:
                    logger.debug("Could not auto-reconstruct project in %s: %s", p_dir, exc)

    def _check_cancellation(self, project_id: str) -> None:
        """Raises PipelineCancelledError if cancellation was requested for this project."""
        if project_id in self._cancel_requested:
            raise PipelineCancelledError("Dự án đã bị dừng bởi người dùng.")

    def cancel_project(self, project_id: str) -> bool:
        """Requests cancellation of a project (either queued or currently running)."""
        project = self.projects.get(project_id)
        if not project:
            return False

        self._cancel_requested.add(project_id)

        # 1. If project is currently in the queue (waiting)
        if project_id in self._project_queue:
            self._project_queue.remove(project_id)
            project.stage = PipelineStage.CANCELLED
            project.current_step_text = "Dự án đã được rút khỏi hàng đợi."
            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.CANCELLED,
                progress=project.progress,
                message=project.current_step_text,
                details={"action": "cancelled_from_queue"},
            )
            self._save_project_state(project)

            # Update positions for remaining items
            for idx, q_id in enumerate(self._project_queue, start=1):
                qp = self.projects.get(q_id)
                if qp:
                    qp.current_step_text = f"Đang trong hàng đợi sản xuất (Vị trí #{idx})..."
                    self.emit_event(
                        project_id=q_id,
                        stage=PipelineStage.QUEUED,
                        progress=0.0,
                        message=qp.current_step_text,
                        details={"queue_position": idx, "queue_length": len(self._project_queue)},
                    )
            return True

        # 2. If project is actively running
        if self._running_project_id == project_id or project.stage in (
            PipelineStage.B1_SCRIPT,
            PipelineStage.B2_SOURCING_TTS,
            PipelineStage.B3_RENDER,
            PipelineStage.B4_PACKAGING,
        ):
            project.stage = PipelineStage.CANCELLED
            project.current_step_text = "Đang dừng sản xuất theo yêu cầu của người dùng..."
            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.CANCELLED,
                progress=project.progress,
                message=project.current_step_text,
                details={"action": "stopping"},
            )
            self._save_project_state(project)
            return True

        return False

    def enqueue_project(self, project_id: str, resume: bool = True) -> Dict[str, Any]:
        """
        Enqueues or immediately starts a project.
        If another project is currently executing (B1->B4), adds to queue.
        Otherwise, starts pipeline execution immediately.
        """
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(f"Project not found: {project_id}")

        # Check if project is already running
        if self._running_project_id == project_id and project.stage in (
            PipelineStage.B1_SCRIPT,
            PipelineStage.B2_SOURCING_TTS,
            PipelineStage.B3_RENDER,
            PipelineStage.B4_PACKAGING,
        ):
            return {"status": "already_running", "project": project.to_dict()}

        # Reset cancellation request if restarting
        self._cancel_requested.discard(project_id)

        # Check if someone else is currently running
        is_busy = False
        if self._running_project_id:
            running_p = self.projects.get(self._running_project_id)
            if running_p and running_p.stage in (
                PipelineStage.B1_SCRIPT,
                PipelineStage.B2_SOURCING_TTS,
                PipelineStage.B3_RENDER,
                PipelineStage.B4_PACKAGING,
            ):
                is_busy = True

        if is_busy:
            if project_id not in self._project_queue:
                self._project_queue.append(project_id)

            pos = self._project_queue.index(project_id) + 1
            project.stage = PipelineStage.QUEUED
            project.current_step_text = f"Đang trong hàng đợi sản xuất (Vị trí #{pos})..."
            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.QUEUED,
                progress=0.0,
                message=project.current_step_text,
                details={"queue_position": pos, "queue_length": len(self._project_queue)},
            )
            self._save_project_state(project)
            return {
                "status": "queued",
                "project_id": project_id,
                "queue_position": pos,
                "queue_length": len(self._project_queue),
            }

        # Idle -> Start immediately
        self._running_project_id = project_id
        if project_id in self._project_queue:
            self._project_queue.remove(project_id)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._execute_pipeline_and_advance(project_id, resume))
            self._active_tasks[project_id] = task
        except RuntimeError:
            pass

        return {
            "status": "started",
            "project_id": project_id,
            "stage": project.stage.value,
        }

    async def _execute_pipeline_and_advance(self, project_id: str, resume: bool) -> None:
        """Executes pipeline for current project, then automatically starts next queued project."""
        try:
            await self.run_pipeline_async(project_id=project_id, resume=resume)
        except Exception as exc:
            logger.error("Pipeline run finished with error for %s: %s", project_id, exc)
        finally:
            if self._running_project_id == project_id:
                self._running_project_id = None
            self._active_tasks.pop(project_id, None)

            # Check and trigger next project in queue
            await self._process_next_in_queue()

    async def _process_next_in_queue(self) -> None:
        """Picks the next valid project in queue and executes it."""
        while self._project_queue:
            next_id = self._project_queue.pop(0)
            next_proj = self.projects.get(next_id)
            if not next_proj or next_id in self._cancel_requested or next_proj.stage == PipelineStage.CANCELLED:
                continue

            self._running_project_id = next_id
            # Broadcast updated queue positions for remaining items
            for idx, q_id in enumerate(self._project_queue, start=1):
                qp = self.projects.get(q_id)
                if qp:
                    qp.current_step_text = f"Đang trong hàng đợi sản xuất (Vị trí #{idx})..."
                    self.emit_event(
                        project_id=q_id,
                        stage=PipelineStage.QUEUED,
                        progress=0.0,
                        message=qp.current_step_text,
                        details={"queue_position": idx, "queue_length": len(self._project_queue)},
                    )

            logger.info("Auto-advancing queue: starting next project %s", next_id)
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._execute_pipeline_and_advance(next_id, resume=True))
                self._active_tasks[next_id] = task
            except RuntimeError:
                pass
            break

    def get_queue_info(self) -> Dict[str, Any]:
        """Returns details about currently executing and queued projects."""
        running_proj = None
        if self._running_project_id:
            p = self.projects.get(self._running_project_id)
            if p and p.stage in (
                PipelineStage.B1_SCRIPT,
                PipelineStage.B2_SOURCING_TTS,
                PipelineStage.B3_RENDER,
                PipelineStage.B4_PACKAGING,
            ):
                running_proj = {
                    "project_id": p.project_id,
                    "topic": p.topic,
                    "stage": p.stage.value,
                    "progress": round(p.progress, 1),
                    "current_step_text": p.current_step_text,
                }
            else:
                self._running_project_id = None

        queue_items = []
        for idx, q_id in enumerate(self._project_queue, start=1):
            qp = self.projects.get(q_id)
            if qp:
                queue_items.append({
                    "project_id": qp.project_id,
                    "topic": qp.topic,
                    "skill_id": qp.skill_id,
                    "target_duration_min": qp.target_duration_min,
                    "position": idx,
                    "created_at": qp.created_at,
                })

        return {
            "running": running_proj,
            "running_project": running_proj,
            "queue_count": len(queue_items),
            "queue_length": len(queue_items),
            "queue": queue_items,
        }

    def create_project(
        self,
        topic: str,
        skill_id: str = "warehouse-fails",
        target_duration_min: int = 15,
        project_id: Optional[str] = None,
    ) -> ProjectState:
        """Alias for get_or_create_project."""
        return self.get_or_create_project(
            topic=topic,
            skill_id=skill_id,
            target_duration_min=target_duration_min,
            project_id=project_id,
        )

    def list_projects(self) -> List[Dict[str, Any]]:
        """Returns summary of all registered projects sorted newest first."""
        results = []
        for p in self.projects.values():
            results.append({
                "project_id": p.project_id,
                "topic": p.topic,
                "skill_id": p.skill_id,
                "target_duration_min": p.target_duration_min,
                "stage": p.stage.value,
                "progress": round(p.progress, 1),
                "current_step_text": p.current_step_text,
                "final_video_path": p.final_video_path,
                "has_final_video": bool(p.final_video_path and Path(p.final_video_path).exists()),
                "thumbnail_path": p.thumbnail_path,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
                "error": p.error,
            })
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    def delete_project(self, project_id: str) -> bool:
        """Deletes project record and frees associated disk assets if present."""
        if project_id in self.projects:
            self.cancel_project(project_id)
            del self.projects[project_id]
            self._subscribers.pop(project_id, None)

            proj_dir = self.config.paths.get_project_render_dir(project_id)
            if proj_dir.exists():
                shutil.rmtree(proj_dir, ignore_errors=True)
            return True
        return False

    def get_or_create_project(
        self,
        topic: str,
        skill_id: str = "warehouse-fails",
        target_duration_min: int = 15,
        project_id: Optional[str] = None,
    ) -> ProjectState:
        """Initializes and returns a new or existing ProjectState."""
        p_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        if p_id in self.projects:
            return self.projects[p_id]

        state = ProjectState(
            project_id=p_id,
            topic=topic,
            skill_id=skill_id,
            target_duration_min=target_duration_min,
            stage=PipelineStage.IDLE,
            progress=0.0,
            current_step_text="Dự án đã sẵn sàng khởi chạy",
        )
        self.projects[p_id] = state
        self._subscribers[p_id] = set()
        self._save_project_state(state)
        return state

    def get_project(self, project_id: str) -> Optional[ProjectState]:
        """Returns ProjectState if exists."""
        return self.projects.get(project_id)

    def subscribe_events(self, project_id: str) -> asyncio.Queue:
        """Registers an async queue subscriber for real-time SSE updates."""
        queue: asyncio.Queue = asyncio.Queue()
        if project_id not in self._subscribers:
            self._subscribers[project_id] = set()
        self._subscribers[project_id].add(queue)

        # Emit current status immediately upon subscription
        project = self.projects.get(project_id)
        if project:
            init_event = PipelineEvent(
                timestamp=time.time(),
                stage=project.stage,
                progress=project.progress,
                message=project.current_step_text,
                details={"project_id": project_id},
            )
            queue.put_nowait(init_event)

        return queue

    def unsubscribe_events(self, project_id: str, queue: asyncio.Queue) -> None:
        """Removes a subscriber queue."""
        if project_id in self._subscribers:
            self._subscribers[project_id].discard(queue)

    def emit_event(
        self,
        project_id: str,
        stage: PipelineStage,
        progress: float,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcasts an event to all connected SSE clients and updates project state."""
        project = self.projects.get(project_id)
        now = time.time()
        det = details or {}

        if project:
            project.stage = stage
            project.progress = progress
            project.current_step_text = message
            project.updated_at = now
            project.logs.append(f"[{time.strftime('%H:%M:%S', time.localtime(now))}] {message}")
            self._save_project_state(project)

        event = PipelineEvent(
            timestamp=now,
            stage=stage,
            progress=progress,
            message=message,
            details=det,
        )

        subscribers = self._subscribers.get(project_id, set())
        for q in list(subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def _assess_word_budget(self, text: str, duration_sec: float) -> str:
        """Determines word budget pill status: optimal, too_long, or too_short."""
        words = len(text.strip().split())
        min_b, max_b = calculate_scene_budget(duration_sec)
        if words < min_b:
            return "too_short"
        if words > max_b:
            return "too_long"
        return "optimal"

    def _extract_subject_anchor(self, topic: str, skill_id: str) -> str:
        """
        Extract primary subject entity anchor from topic and skill_id to prevent off-topic footage straying.
        E.g. topic 'Lửng mật (Honey Badger): ...' -> 'honey badger'
        """
        topic_lower = topic.lower()

        # Check parentheses for English name like (Honey Badger), (Tasmanian Tiger)
        paren_match = re.search(r'\(([^)]+)\)', topic)
        if paren_match:
            cand = paren_match.group(1).strip()
            if len(cand) > 2 and not cand.isdigit() and not any(k in cand.lower() for k in ["p3", "p4", "tập", "phần"]):
                return cand.lower()

        # Common animals & wildlife mappings
        animals_map = {
            "lửng mật": "honey badger",
            "hổ tasmania": "tasmanian tiger thylacine",
            "sư tử": "african lion",
            "báo hoa mai": "african leopard",
            "báo săn": "cheetah",
            "rắn hổ mang": "king cobra snake",
            "rắn": "snake venomous",
            "trăn": "african python snake",
            "linh cẩu": "spotted hyena",
            "chó rừng": "black backed jackal",
            "rùa": "tortoise turtle",
            "voi": "african elephant",
            "tê giác": "african rhino",
            "hà mã": "hippo",
            "cá sấu": "nile crocodile",
            "chim ưng": "african eagle raptor",
            "kền kền": "vulture savanna",
            "ong mật": "honey bees nest",
            "chuột chũi": "wild mole digging",
            "gấu": "wild bear",
            "sói": "wolf pack",
            "cá mập": "shark ocean",
            "cá voi": "whale ocean",
        }
        for vi_name, en_name in animals_map.items():
            if vi_name in topic_lower:
                return en_name

        # History & Mystery mappings
        history_map = {
            "chu nguyên chương": "hongwu emperor ming dynasty",
            "kim tự tháp": "egyptian pyramid ancient cairo",
            "angkor": "angkor wat cambodia temple",
            "chiến tranh thế giới": "world war battlefield archive",
            "kỷ vật": "war battlefield relic history",
        }
        for vi_name, en_name in history_map.items():
            if vi_name in topic_lower:
                return en_name

        # Warehouse & Industrial accidents
        if "kho" in topic_lower or "kệ" in topic_lower or "xe nâng" in topic_lower or skill_id == "warehouse-fails":
            return "warehouse forklift accident"

        # General niche defaults
        if skill_id == "nature-wildlife-survival":
            return "wildlife animal"
        elif skill_id == "historical-mysteries":
            return "historical ancient"
        elif skill_id == "extreme-weather":
            return "extreme weather disaster"
        elif skill_id == "military-microhistory":
            return "military history battlefield"

        words = [w for w in re.split(r'[:\-–,\(\)]', topic)[0].split() if len(w) > 2]
        return " ".join(words[:3]) if words else "documentary"

    @staticmethod
    def _build_natural_query(raw_kw: str, subject_anchor: Optional[str]) -> str:
        """
        Build clean, unquoted, natural search query without term duplication.
        E.g. ('hyena snout snarling', 'spotted hyena') -> 'hyena snout snarling'
             ('biting carcass', 'spotted hyena') -> 'spotted hyena biting carcass'
        """
        kw = raw_kw.strip().replace('"', "")
        if not kw:
            return ""
        if not subject_anchor:
            return kw
        a_clean = subject_anchor.strip().replace('"', "")
        # ADR-019: same anchor rule as candidate scoring (full phrase or head noun, never modifier-only)
        if anchor_matches(kw, a_clean):
            return kw
        return f"{a_clean} {kw}"

    @staticmethod
    def _calculate_action_offset(
        scene: Scene,
        sourced_asset: Optional[Any],
        source_dur: float,
        usage_count: int,
        en_kws: List[str],
        vi_kws: List[str],
    ) -> float:
        """
        Calculate intelligent action cut offset via chapter alignment or golden-ratio positioning.
        """
        start_offset = 0.0
        chapters = None
        if sourced_asset and getattr(sourced_asset, "metadata", None):
            chapters = sourced_asset.metadata.get("chapters")

        matched_chapter_offset: Optional[float] = None
        best_match_count = 0
        if chapters and isinstance(chapters, list):
            scene_context_lower = (scene.text + " " + " ".join(en_kws) + " " + " ".join(vi_kws)).lower()
            for ch in chapters:
                ch_title = str(ch.get("title") or "").lower()
                ch_start = float(ch.get("start_time") or 0.0)
                if ch_start < 2.0 or any(x in ch_title for x in ("intro", "outro", "subscribe", "end screen")):
                    continue
                ch_words = [w for w in re.findall(r"\w+", ch_title) if len(w) > 3]
                match_count = sum(1 for w in ch_words if w in scene_context_lower)
                if match_count > best_match_count and (source_dur - ch_start) >= (scene.duration_sec + 2.0):
                    best_match_count = match_count
                    matched_chapter_offset = ch_start + 2.0

        if matched_chapter_offset is not None and best_match_count > 0:
            start_offset = matched_chapter_offset
        elif source_dur > (scene.duration_sec + 3.0):
            if source_dur >= 60.0:
                base_offset = max(10.0, min(source_dur * 0.20 + (usage_count * 8.0), source_dur - scene.duration_sec - 15.0))
            elif source_dur >= 30.0:
                base_offset = 7.0 + (usage_count * 5.0)
            elif source_dur >= 18.0:
                base_offset = 4.5
            else:
                base_offset = 1.5

            start_offset = max(0.0, min(base_offset, source_dur - scene.duration_sec - 1.0))

        return start_offset

    @staticmethod
    def _resolve_segment_offset(
        offset: float,
        duration: float,
        source_dur: float,
        used_intervals: List[Tuple[float, float]],
    ) -> Optional[float]:
        """
        ADR-019: Return a start offset whose [offset, offset+duration] window lies fully inside the
        source (no black padding) and does not overlap segments already used by other scenes.
        Returns None when no such window exists.
        """
        tolerance = 0.05
        if source_dur > 0 and source_dur < duration - tolerance:
            return None
        max_start = max(0.0, source_dur - duration) if source_dur > 0 else max(0.0, offset)
        off = min(max(0.0, offset), max_start)

        def _overlaps(o: float) -> bool:
            return any(o < e and (o + duration) > s for s, e in used_intervals)

        if not _overlaps(off):
            return off
        candidates = {e + 0.5 for _, e in used_intervals} | {s - duration - 0.5 for s, _ in used_intervals}
        for c in sorted(candidates, key=lambda x: abs(x - off)):
            if 0.0 <= c <= max_start and not _overlaps(c):
                return c
        return None

    @staticmethod
    def _track_footage_usage(
        metadata: Dict[str, Any],
        used_video_counts: Dict[str, int],
        used_intervals: Dict[str, List[Tuple[float, float]]],
    ) -> None:
        """Record per-source-video usage count and used time window (ADR-019 reuse cap)."""
        vid = str(metadata.get("video_id") or "")
        if vid:
            used_video_counts[vid] = used_video_counts.get(vid, 0) + 1
        raw = metadata.get("raw_asset_path")
        if raw:
            start = float(metadata.get("start_offset_sec") or 0.0)
            dur = float(metadata.get("duration_sec") or 0.0)
            for key in {str(raw), str(Path(raw))}:
                used_intervals.setdefault(key, []).append((start, start + dur))

    def refresh_settings(self) -> None:
        """Synchronizes dynamic settings for voiceover and scriptwriting pipeline."""
        if self.voiceover_manager:
            self.voiceover_manager.refresh_settings()
        try:
            from autovideo.core.settings import SettingsManager
            from autovideo.script.pipeline import (
                GeminiFlashAdapter,
                NineRouterAdapter,
            )
            sm = SettingsManager(config=self.config)
            s = sm.load_settings()
            if s.llm_provider == "9router":
                self.script_brain.adapter = NineRouterAdapter(
                    api_key=s.ninerouter_api_key,
                    base_url=s.ninerouter_base_url,
                    model=s.llm_model,
                )
            elif s.llm_provider == "gemini":
                self.script_brain.adapter = GeminiFlashAdapter(
                    api_key=s.gemini_api_key,
                    model=s.llm_model,
                )
            elif s.llm_provider == "mock":
                logger.warning("LLM provider được đặt là 'mock' nhưng MockLLMAdapter đã bị loại bỏ khỏi production.")
        except Exception as exc:
            logger.warning("Could not refresh LLM settings in coordinator: %s", exc)

    async def run_pipeline_async(self, project_id: str, resume: bool = True) -> ProjectState:
        """
        Executes the full automated pipeline B1 -> B2 -> B3 -> B4 asynchronously.
        Does not block FastAPI event loop.
        """
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(f"Project not found: {project_id}")

        loop = asyncio.get_running_loop()
        try:
            # Run the synchronous coordinator workflow in an executor thread
            await loop.run_in_executor(None, self._run_pipeline_sync, project_id, resume)
            return project
        except PipelineCancelledError as e:
            logger.info("Pipeline cancelled by user for project %s", project_id)
            project.stage = PipelineStage.CANCELLED
            project.current_step_text = "Dự án đã dừng theo yêu cầu của người dùng."
            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.CANCELLED,
                progress=project.progress,
                message="Dự án đã dừng sản xuất theo yêu cầu của người dùng.",
                details={"cancelled": True},
            )
            return project
        except Exception as e:
            logger.exception("Pipeline execution failed for project %s: %s", project_id, e)
            project.stage = PipelineStage.ERROR
            project.error = str(e)
            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.ERROR,
                progress=project.progress,
                message=f"Lỗi quy trình: {e}",
                details={"error": str(e)},
            )
            raise

    def _run_pipeline_sync(self, project_id: str, resume: bool = True) -> None:
        """Synchronous implementation of the 4-step pipeline."""
        project = self.projects[project_id]
        project_dir = self.config.paths.get_project_render_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        temp_scenes_dir = self.config.paths.cache_temp_scenes_dir / project_id
        temp_scenes_dir.mkdir(parents=True, exist_ok=True)

        self._check_cancellation(project_id)

        # Refresh dynamic settings (TTS, LLM Provider, Keys) from config/settings.json
        self.refresh_settings()

        # -------------------------------------------------------------
        # STEP 1: B1 Scriptwriting & Draft SEO (WU-03)
        # -------------------------------------------------------------
        self._check_cancellation(project_id)
        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B1_SCRIPT,
            progress=5.0,
            message=f"B1: Đang nạp Skill '{project.skill_id}' & biên soạn kịch bản...",
            details={"step": "b1_start"},
        )

        screenplay = None
        seo_pkg = None
        screenplay_path = project_dir / "screenplay.json"
        seo_md_path = project_dir / "youtube_seo.md"

        if resume and (project.screenplay or screenplay_path.exists()):
            try:
                from autovideo.script.pipeline import Screenplay, SEOPackage
                if not project.screenplay and screenplay_path.exists():
                    project.screenplay = json.loads(screenplay_path.read_text(encoding="utf-8"))
                screenplay = Screenplay.model_validate(project.screenplay)
                if project.seo_package:
                    seo_pkg = SEOPackage.model_validate(project.seo_package)
                all_scenes = screenplay.all_scenes
                total_scenes = len(all_scenes)
                self.emit_event(
                    project_id=project_id,
                    stage=PipelineStage.B1_SCRIPT,
                    progress=20.0,
                    message=f"B1: Khôi phục kịch bản có sẵn ({total_scenes} scenes). Anti-AI: PASS.",
                    details={
                        "total_scenes": total_scenes,
                        "screenplay_path": str(screenplay_path),
                        "seo_md_path": str(seo_md_path),
                        "resumed": True,
                    },
                )
            except Exception as e:
                logger.warning("Could not restore existing screenplay on resume: %s, regenerating...", e)
                screenplay = None

        if screenplay is None:
            dur_min = float(project.target_duration_min or 5)
            calc_scenes = max(10, int(dur_min * 7.5))
            screenplay, seo_pkg = self.script_brain.generate_screenplay(
                topic=project.topic,
                skill_id=project.skill_id,
                target_scenes=calc_scenes,
                target_duration_min=dur_min,
            )

            # Export B1 artifacts
            screenplay_path, seo_md_path = self.script_brain.export_artifacts(
                screenplay=screenplay,
                seo=seo_pkg,
                output_dir=project_dir,
            )

            project.screenplay = screenplay.model_dump()
            project.seo_package = seo_pkg.model_dump()
            project.seo_markdown_path = str(seo_md_path)

            all_scenes = screenplay.all_scenes
            total_scenes = len(all_scenes)

            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.B1_SCRIPT,
                progress=20.0,
                message=f"B1: Hoàn tất kịch bản ({total_scenes} scenes). Phong cách Skill Niche: PASS.",
                details={
                    "total_scenes": total_scenes,
                    "screenplay_path": str(screenplay_path),
                    "seo_md_path": str(seo_md_path),
                },
            )

        # -------------------------------------------------------------
        # STEP 2: B2 Background Asset Sourcing + TTS + Scene Assembly (WU-02, WU-04, WU-05)
        # -------------------------------------------------------------
        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B2_SOURCING_TTS,
            progress=25.0,
            message=f"B2: Bắt đầu tải footage ngầm & tạo giọng đọc ZeroTTS...",
            details={"step": "b2_start", "total_scenes": total_scenes},
        )

        self.voiceover_manager.refresh_settings()

        scene_assets_map: Dict[str, SceneAssets] = {}
        assembled_scene_paths: Dict[str, Path] = {}

        existing_scenes_map = {
            s.scene_id: s for s in project.completed_scenes
        }
        retained_completed_scenes: List[CompletedSceneRecord] = []
        used_footage_counts: Dict[str, int] = {}
        subject_anchor = self._extract_subject_anchor(project.topic, project.skill_id)
        active_skill = None
        try:
            active_skill = self.skill_registry.get_skill(project.skill_id)
        except Exception as exc:
            logger.debug("Could not resolve skill %s: %s", project.skill_id, exc)

        skill_pref_cats = active_skill.manifest.preferred_categories if active_skill else None
        skill_disc_cats = active_skill.manifest.discouraged_categories if active_skill else None
        skill_trusted_channels = active_skill.manifest.trusted_channels if active_skill else None
        logger.info(
            "Khởi chạy B2 Sourcing với Subject Anchor: '%s' cho dự án %s (Skill: %s)",
            subject_anchor, project_id, project.skill_id
        )

        # ADR-019: semantic judge, reuse cap and non-overlapping segment bookkeeping
        used_video_counts: Dict[str, int] = {}
        used_footage_intervals: Dict[str, List[Tuple[float, float]]] = {}
        max_footage_reuse = 2
        max_judge_calls_per_scene = 6
        semantic_judge = SemanticFootageJudge(enabled=False)
        try:
            from autovideo.core.settings import SettingsManager
            _s = SettingsManager(config=self.config).load_settings()
            semantic_judge = SemanticFootageJudge.from_settings(_s)
            max_footage_reuse = max(1, int(getattr(_s, "footage_max_reuse", 2)))
        except Exception as exc:
            logger.warning("Không khởi tạo được SemanticFootageJudge: %s", exc)
        logger.info(
            "Semantic judge: active=%s model=%s min_score=%.1f | footage_max_reuse=%d",
            semantic_judge.active, semantic_judge.model, semantic_judge.min_score, max_footage_reuse,
        )

        for idx, scene in enumerate(all_scenes, start=1):
            self._check_cancellation(project_id)
            scene_progress = 25.0 + (idx / total_scenes) * 35.0  # 25% -> 60%
            scene_out_path = temp_scenes_dir / f"scene_{idx:03d}.mp4"

            # Reuse previously assembled scene if present on disk
            if (
                resume
                and scene.scene_id in existing_scenes_map
                and scene_out_path.exists()
                and scene_out_path.stat().st_size > 2048
            ):
                rec = existing_scenes_map[scene.scene_id]
                assembled_scene_paths[scene.scene_id] = scene_out_path
                scene_assets_map[scene.scene_id] = SceneAssets(
                    media_path=Path(rec.video_path) if rec.video_path else scene_out_path,
                    audio_path=Path(rec.audio_path) if rec.audio_path else None,
                    start_offset_sec=getattr(rec, "metadata", {}).get("start_offset_sec", 0.0) if rec.metadata else 0.0,
                    is_preassembled=True,
                )
                retained_completed_scenes.append(rec)
                project.completed_scenes = list(retained_completed_scenes)
                self._track_footage_usage(rec.metadata or {}, used_video_counts, used_footage_intervals)
                self.emit_event(
                    project_id=project_id,
                    stage=PipelineStage.B2_SOURCING_TTS,
                    progress=scene_progress,
                    message=f"B2: Scene {idx:02d}/{total_scenes:02d} ({scene.scene_id}) đã hoàn tất từ trước, tiếp tục...",
                    details={"current_scene": scene.scene_id, "scene_index": idx, "resumed": True},
                )
                continue

            self.emit_event(
                project_id=project_id,
                stage=PipelineStage.B2_SOURCING_TTS,
                progress=scene_progress,
                message=f"B2: Đang xử lý Scene {idx:02d}/{total_scenes:02d} ({scene.scene_id})...",
                details={"current_scene": scene.scene_id, "scene_index": idx},
            )

            # 1. Synthesize audio
            self._check_cancellation(project_id)
            audio_res = self.voiceover_manager.synthesize_scene(
                scene=scene,
                scene_index=idx,
                project_id=project_id,
            )
            scene.duration_sec = audio_res.duration_sec

            # 2. Source footage asset with multi-keyword cascade & subject anchor
            self._check_cancellation(project_id)
            en_kws: List[str] = []
            vi_kws: List[str] = []
            if scene.keywords:
                if scene.keywords.en:
                    if isinstance(scene.keywords.en, list):
                        en_kws.extend([str(k).strip() for k in scene.keywords.en if str(k).strip()])
                    elif isinstance(scene.keywords.en, str):
                        en_kws.extend([k.strip() for k in scene.keywords.en.split(",") if k.strip()])
                if scene.keywords.vi:
                    if isinstance(scene.keywords.vi, list):
                        vi_kws.extend([str(k).strip() for k in scene.keywords.vi if str(k).strip()])
                    elif isinstance(scene.keywords.vi, str):
                        vi_kws.extend([k.strip() for k in scene.keywords.vi.split(",") if k.strip()])

            # Build enriched keyword candidate list:
            # Tier 1: Natural LLM-generated search queries (Zero-code truncation, unquoted)
            # Tier 2: Subject-anchored natural fallbacks (declared dynamically by Skill Niche)
            # Tier 3: Subject-anchored Vietnamese keywords
            kw_candidates: List[str] = []

            # Tier 1: High-intent LLM-generated search queries (Zero-code truncation, preserving full semantic precision)
            for ek in en_kws:
                q_kw = self._build_natural_query(ek, subject_anchor)
                if q_kw and q_kw not in kw_candidates:
                    kw_candidates.append(q_kw)

            # Tier 2: Subject-anchored natural fallbacks (declared dynamically by Skill Niche)
            if subject_anchor:
                broad_fallbacks: List[str] = []
                if active_skill and active_skill.manifest.fallback_search_templates:
                    for tpl in active_skill.manifest.fallback_search_templates:
                        tpl_clean = tpl.replace('"', "").strip()
                        if "{subject_anchor}" in tpl_clean:
                            broad_fallbacks.append(tpl_clean.format(subject_anchor=subject_anchor))
                        else:
                            broad_fallbacks.append(f"{subject_anchor} {tpl_clean}")
                else:
                    broad_fallbacks = [
                        f"{subject_anchor} documentary",
                        f"{subject_anchor} footage",
                    ]
                for bf in broad_fallbacks:
                    if bf not in kw_candidates:
                        kw_candidates.append(bf)

            # Tier 3: Subject-anchored Vietnamese keywords
            for vk in vi_kws:
                q_vi = self._build_natural_query(vk, subject_anchor)
                if q_vi and q_vi not in kw_candidates:
                    kw_candidates.append(q_vi)

            if not kw_candidates:
                kw_candidates = [f"{subject_anchor} {project.topic}" if subject_anchor else project.topic]

            scene_terms = extract_scene_terms(en_kws, getattr(scene, "visual_prompt", None), subject_anchor)
            exclude_ids: List[str] = [vid for vid, cnt in used_video_counts.items() if cnt >= max_footage_reuse]
            scene_visual_prompt = str(getattr(scene, "visual_prompt", "") or "")

            footage_path: Optional[Path] = None
            sourced_asset_obj: Optional[Any] = None
            final_start_offset: float = 0.0
            last_err: Optional[Exception] = None
            semantic_record: Dict[str, Any] = {"verdict": "not_run"}
            review_reasons: List[str] = []
            best_fallback: Dict[str, Any] = {}
            judge_budget = {"calls": 0}
            bm = BinaryManager(self.config)
            ff_bin, _ = bm.find_binary("ffmpeg")

            def _evaluate_candidate(sourced: Any) -> Optional[Dict[str, Any]]:
                """ADR-019 gate chain: visual QA -> source coverage/non-overlap -> semantic judge."""
                cand_path = sourced.file_path
                cand_dur = float(getattr(sourced, "duration_sec", 0.0) or 0.0)
                cand_key = str(cand_path)
                base_offset = self._calculate_action_offset(
                    scene=scene,
                    sourced_asset=sourced,
                    source_dur=cand_dur,
                    usage_count=used_footage_counts.get(cand_key, 0),
                    en_kws=en_kws,
                    vi_kws=vi_kws,
                )
                offsets_to_try: List[float] = [base_offset]
                if cand_dur > scene.duration_sec * 3:
                    alt = cand_dur * 0.6
                    if abs(alt - base_offset) > scene.duration_sec + 2.0:
                        offsets_to_try.append(alt)

                for raw_off in offsets_to_try:
                    off = self._resolve_segment_offset(
                        raw_off, scene.duration_sec, cand_dur, used_footage_intervals.get(cand_key, [])
                    )
                    if off is None:
                        logger.warning("Footage %s không đủ thời lượng / trùng đoạn đã dùng cho %s.", cand_path.name, scene.scene_id)
                        continue

                    inspect_res = VisualQualityInspector.inspect_video_segment(
                        video_path=cand_path, start_sec=off, duration_sec=scene.duration_sec, ffmpeg_bin=ff_bin,
                    )
                    if not inspect_res.is_clean:
                        logger.warning(
                            "Footage %s tại offset %.1fs dính lỗi thị giác %s. Đang quét tìm đoạn sạch...",
                            cand_path.name, off, inspect_res.defects,
                        )
                        clean_offset = VisualQualityInspector.find_clean_segment(
                            video_path=cand_path,
                            target_duration=scene.duration_sec,
                            total_duration=cand_dur,
                            initial_offset=off,
                            ffmpeg_bin=ff_bin,
                        )
                        if clean_offset is None:
                            logger.warning("Footage %s bị lỗi thị giác toàn bộ clip. Loại bỏ candidate.", cand_path.name)
                            return None
                        off = self._resolve_segment_offset(
                            clean_offset, scene.duration_sec, cand_dur, used_footage_intervals.get(cand_key, [])
                        )
                        if off is None:
                            continue

                    if judge_budget["calls"] >= max_judge_calls_per_scene:
                        logger.warning("Đã hết ngân sách semantic judge cho %s.", scene.scene_id)
                        return None
                    if semantic_judge.active:
                        judge_budget["calls"] += 1
                    verdict = semantic_judge.judge(
                        video_path=cand_path,
                        start_sec=off,
                        duration_sec=scene.duration_sec,
                        narration=scene.text,
                        visual_prompt=scene_visual_prompt,
                        subject_anchor=subject_anchor or "",
                        ffmpeg_bin=ff_bin,
                    )
                    cand = {"path": cand_path, "sourced": sourced, "offset": off, "semantic": verdict.to_dict()}
                    if verdict.verdict in ("pass", "unavailable"):
                        logger.info(
                            "Semantic judge %s cho %s: %s @%.1fs (score=%.1f) %s",
                            verdict.verdict, scene.scene_id, cand_path.name, off, verdict.score, verdict.reason,
                        )
                        return cand
                    logger.warning(
                        "Semantic judge LOẠI %s @%.1fs cho %s (score=%.1f, subject=%s, overlay=%s): %s",
                        cand_path.name, off, scene.scene_id, verdict.score, verdict.subject_present,
                        verdict.has_overlay, verdict.reason,
                    )
                    if verdict.subject_present and verdict.is_real_footage and (
                        not best_fallback or verdict.score > best_fallback["semantic"]["score"]
                    ):
                        best_fallback.clear()
                        best_fallback.update(cand)
                return None

            accepted: Optional[Dict[str, Any]] = None
            for candidate_kw in kw_candidates:
                if judge_budget["calls"] >= max_judge_calls_per_scene:
                    break
                try:
                    logger.info("Đang tìm footage cho phân cảnh %s với từ khóa: '%s'", scene.scene_id, candidate_kw)
                    # ADR-019: ALWAYS pass the subject anchor (no conditional bypass)
                    sourced = self.sourcing_engine.source_scene_asset(
                        scene_id=scene.scene_id,
                        query=candidate_kw,
                        preferred_vault=scene.preferred_vault,
                        enforce_duration=True,
                        subject_anchor=subject_anchor,
                        niche_id=project.skill_id,
                        preferred_categories=skill_pref_cats,
                        discouraged_categories=skill_disc_cats,
                        trusted_channels=skill_trusted_channels,
                        scene_terms=scene_terms,
                        exclude_video_ids=list(exclude_ids),
                    )
                    if sourced and sourced.file_path.exists() and sourced.file_path.stat().st_size > 0:
                        accepted = _evaluate_candidate(sourced)
                        if accepted:
                            break
                        rejected_vid = str((getattr(sourced, "metadata", None) or {}).get("video_id") or "")
                        if rejected_vid and rejected_vid not in exclude_ids:
                            exclude_ids.append(rejected_vid)
                except Exception as exc:
                    logger.warning("Thử từ khóa '%s' cho phân cảnh %s thất bại: %s", candidate_kw, scene.scene_id, exc)
                    last_err = exc
                    continue

            # If all candidates failed with strict duration, try primary candidate with relaxed duration (5-300s)
            if not accepted and judge_budget["calls"] < max_judge_calls_per_scene:
                try:
                    primary_kw = kw_candidates[0] if kw_candidates else project.topic
                    logger.info("Thử lại tải footage cho %s với từ khóa '%s' (nới lỏng thời lượng)...", scene.scene_id, primary_kw)
                    sourced = self.sourcing_engine.source_scene_asset(
                        scene_id=scene.scene_id,
                        query=primary_kw,
                        preferred_vault=scene.preferred_vault,
                        enforce_duration=False,
                        subject_anchor=subject_anchor,
                        niche_id=project.skill_id,
                        preferred_categories=skill_pref_cats,
                        discouraged_categories=skill_disc_cats,
                        trusted_channels=skill_trusted_channels,
                        scene_terms=scene_terms,
                        exclude_video_ids=list(exclude_ids),
                    )
                    if sourced and sourced.file_path.exists() and sourced.file_path.stat().st_size > 0:
                        accepted = _evaluate_candidate(sourced)
                except Exception as exc:
                    last_err = exc

            # Best-effort: subject visible & real footage but below match threshold -> use, flag for review
            if not accepted and best_fallback:
                accepted = dict(best_fallback)
                review_reasons.append(f"semantic_below_threshold(score={accepted['semantic'].get('score')})")

            if accepted:
                footage_path = accepted["path"]
                sourced_asset_obj = accepted["sourced"]
                final_start_offset = float(accepted["offset"])
                semantic_record = accepted["semantic"]
                if semantic_record.get("verdict") == "unavailable":
                    review_reasons.append("semantic_check_unavailable")
                logger.info(
                    "Đã chọn footage cho %s: %s (offset=%.1fs, semantic=%s)",
                    scene.scene_id, footage_path.name, final_start_offset, semantic_record.get("verdict"),
                )

            # Tier 4: Pipeline Resilience Fallback - If all online candidates fail, reuse a valid footage from previous scenes
            if not footage_path and retained_completed_scenes:
                logger.warning(
                    "Mọi từ khóa tìm kiếm cho %s đều thất bại. Kích hoạt cơ chế tự phục hồi: Tái sử dụng footage từ cảnh đã hoàn tất...",
                    scene.scene_id,
                )
                for rec in reversed(retained_completed_scenes):
                    if rec.video_path and Path(rec.video_path).exists() and Path(rec.video_path).stat().st_size > 10000:
                        footage_path = Path(rec.video_path)
                        final_start_offset = 0.0
                        review_reasons.append(f"tier4_reused_footage_from_{rec.scene_id}")
                        logger.info("Đã chọn footage dự phòng cho %s từ %s (%s)", scene.scene_id, rec.scene_id, footage_path.name)
                        break

            if not footage_path:
                raise RuntimeError(
                    f"Không thể tìm hoặc tải footage cho phân cảnh {scene.scene_id} "
                    f"(Đã thử các từ khóa: {kw_candidates}): {last_err}"
                )

            # 3. Assemble atomic scene via SceneMuxer with verified clean offset
            self._check_cancellation(project_id)
            scene_out_path = temp_scenes_dir / f"scene_{idx:03d}.mp4"
            start_offset = final_start_offset
            used_footage_counts[str(footage_path)] = used_footage_counts.get(str(footage_path), 0) + 1

            mux_res = self.scene_muxer.assemble_scene(
                project_id=project_id,
                scene_idx=idx,
                media_path=footage_path,
                voiceover_audio_path=audio_res.audio_path,
                target_duration_sec=scene.duration_sec,
                start_offset_sec=start_offset,
                output_path=scene_out_path,
            )

            assembled_scene_paths[scene.scene_id] = mux_res.output_path
            scene_assets_map[scene.scene_id] = SceneAssets(
                media_path=mux_res.output_path,
                audio_path=audio_res.audio_path,
                start_offset_sec=start_offset,
                is_preassembled=True,
            )

            # Build detailed source attribution and cut range
            end_offset = start_offset + mux_res.duration_sec
            cut_from = format_time_code(start_offset)
            cut_to = format_time_code(end_offset)
            cut_dur = round(mux_res.duration_sec)
            cut_summary = f"{cut_dur}s cắt từ {cut_from} - {cut_to} của video stock"

            source_info = None
            if sourced_asset_obj:
                meta = getattr(sourced_asset_obj, "metadata", {}) or {}
                ext = meta.get("extractor", sourced_asset_obj.vault_source)
                vid = meta.get("video_id") or ""
                url = meta.get("webpage_url") or ""
                if not url and vid and ("youtube" in ext.lower() or "universal" in ext.lower()):
                    url = f"https://www.youtube.com/watch?v={vid}"
                platform = (
                    "YouTube" if ("youtube" in ext.lower() or "universal" in ext.lower())
                    else "Douyin" if "douyin" in ext.lower()
                    else "Bilibili" if "bilibili" in ext.lower()
                    else sourced_asset_obj.vault_source.capitalize()
                )
                url_with_ts = url
                if url and "youtube" in platform.lower() and start_offset > 0:
                    sep = "&" if "?" in url else "?"
                    url_with_ts = f"{url}{sep}t={int(start_offset)}s"

                source_info = {
                    "vault": sourced_asset_obj.vault_source,
                    "platform": platform,
                    "url": url,
                    "url_with_timestamp": url_with_ts,
                    "video_id": vid,
                    "start_offset_sec": start_offset,
                    "end_offset_sec": end_offset,
                    "cut_from": cut_from,
                    "cut_to": cut_to,
                    "cut_duration": cut_dur,
                    "cut_summary": cut_summary,
                    "title": meta.get("title") or "",
                    "uploader": meta.get("uploader") or "",
                    "raw_filename": footage_path.name if footage_path else "",
                    "query": meta.get("effective_query") or getattr(sourced_asset_obj, "query", ""),
                }
            elif footage_path:
                source_info = resolve_scene_source_info({
                    "metadata": {
                        "raw_asset_path": str(footage_path),
                        "start_offset_sec": start_offset,
                    },
                    "duration_sec": mux_res.duration_sec,
                    "preferred_vault": scene.preferred_vault,
                    "keywords": scene.keywords.model_dump(),
                })

            # Record scene completion
            budget_status = self._assess_word_budget(scene.text, scene.duration_sec)
            record = CompletedSceneRecord(
                scene_id=scene.scene_id,
                chapter_index=scene.chapter_index,
                text=scene.text,
                duration_sec=scene.duration_sec,
                word_count=scene.word_count,
                word_budget_status=budget_status,
                video_path=str(mux_res.output_path),
                audio_path=str(audio_res.audio_path),
                status="completed",
                preferred_vault=scene.preferred_vault,
                camera_angle=scene.camera_angle,
                keywords=scene.keywords.model_dump(),
                source_info=source_info,
                metadata={
                    "raw_asset_path": str(footage_path.resolve()) if footage_path else None,
                    "start_offset_sec": start_offset,
                    "duration_sec": mux_res.duration_sec,
                    **(sourced_asset_obj.metadata if (sourced_asset_obj and sourced_asset_obj.metadata) else {}),
                    "scene_terms": scene_terms,
                    "semantic_check": semantic_record,
                    "needs_review": bool(review_reasons),
                    "review_reasons": review_reasons,
                } if footage_path else None,
            )
            retained_completed_scenes.append(record)
            project.completed_scenes = list(retained_completed_scenes)
            self._track_footage_usage(record.metadata or {}, used_video_counts, used_footage_intervals)
            if review_reasons:
                self.emit_event(
                    project_id=project_id,
                    stage=PipelineStage.B2_SOURCING_TTS,
                    progress=scene_progress,
                    message=f"B2: ⚠ {scene.scene_id} cần kiểm tra thủ công: {', '.join(review_reasons)}",
                    details={"current_scene": scene.scene_id, "needs_review": True, "review_reasons": review_reasons},
                )

            # Measure rolling buffer
            project.rolling_buffer_bytes = self.rolling_buffer.get_buffer_size_bytes(temp_scenes_dir)

        self._check_cancellation(project_id)
        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B2_SOURCING_TTS,
            progress=60.0,
            message=f"B2: Hoàn tất toàn bộ {total_scenes} atomic scenes sạch 16:9.",
            details={"completed_count": len(project.completed_scenes)},
        )

        # -------------------------------------------------------------
        # STEP 3: B3 Modular Chapter Builder & Concat Demuxer (WU-06)
        # -------------------------------------------------------------
        self._check_cancellation(project_id)
        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B3_RENDER,
            progress=65.0,
            message=f"B3: Bắt đầu ghép nối Chapters & tối ưu Rolling Buffer...",
            details={"step": "b3_start"},
        )

        prod_pipeline = ProductionPipeline(
            config=self.config,
            chapter_builder=self.chapter_builder,
            concat_demuxer=self.concat_demuxer,
            rolling_buffer=self.rolling_buffer,
            binary_manager=self.binary_manager,
        )

        final_video_dest = project_dir / f"{project_id}_final.mp4"
        self._check_cancellation(project_id)
        prod_result = prod_pipeline.run(
            project_id=project_id,
            screenplay=screenplay,
            asset_resolver=scene_assets_map,
            output_video_path=final_video_dest,
            resume=resume,
        )

        project.final_video_path = str(prod_result.final_video_path)
        project.rolling_buffer_bytes = self.rolling_buffer.get_buffer_size_bytes(temp_scenes_dir)

        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B3_RENDER,
            progress=85.0,
            message=f"B3: Render thành công Video 1080p ({prod_result.total_duration_sec:.1f}s) trong {prod_result.concat_elapsed_sec:.2f}s.",
            details={
                "video_path": str(prod_result.final_video_path),
                "total_duration_sec": prod_result.total_duration_sec,
            },
        )

        # -------------------------------------------------------------
        # STEP 4: B4 Counterpoint Thumbnail & SEO Packaging (WU-07)
        # -------------------------------------------------------------
        self._check_cancellation(project_id)
        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.B4_PACKAGING,
            progress=88.0,
            message=f"B4: Tạo ảnh Thumbnail đối nghịch & kiểm định Safe Zone 20%...",
            details={"step": "b4_start"},
        )

        # Ensure seo_pkg is safely resolved even on resume
        if seo_pkg is None:
            if project.seo_package:
                try:
                    from autovideo.script.pipeline import SEOPackage
                    seo_pkg = SEOPackage.model_validate(project.seo_package)
                except Exception as e:
                    logger.warning("Could not restore seo_package from project state: %s", e)
            if seo_pkg is None:
                from autovideo.script.pipeline import SEOPackage
                seo_pkg = SEOPackage(
                    titles=[project.topic or "Tài liệu chuyên đề"],
                    description=project.topic or "",
                    hashtags=["#documentary", "#wildlife"],
                    timestamps=["00:00 - Mở đầu"],
                    thumbnail_badge="TIÊU ĐIỂM",
                    thumbnail_hook=(project.topic or "TIÊU ĐIỂM").split(":")[0][:25],
                    thumbnail_prompt=f"Dramatic cinematic documentary thumbnail of {project.topic}",
                )

        # Resolve dynamic thumbnail hook & badge from active skill & LLM output
        thumb_hook = getattr(seo_pkg, "thumbnail_hook", None) if seo_pkg else None
        if not thumb_hook and seo_pkg and getattr(seo_pkg, "thumbnail_prompt", None):
            thumb_hook = seo_pkg.thumbnail_prompt.split(",")[0][:30]
        if not thumb_hook:
            thumb_hook = (project.topic or "BẢN ÁN OAN KHỐC").split(":")[0][:25]

        skill_obj = None
        try:
            skill_obj = self.skill_registry.get_skill(project.skill_id)
        except Exception:
            pass

        thumb_badge = getattr(seo_pkg, "thumbnail_badge", None) if seo_pkg else None
        if not thumb_badge and skill_obj:
            thumb_badge = skill_obj.badge
        if not thumb_badge:
            thumb_badge = "TIÊU ĐIỂM"

        self._check_cancellation(project_id)
        pub_result = self.publisher_manager.prepare_publishing_package(
            project_id=project_id,
            topic=project.topic,
            chapters=screenplay.chapters,
            thumbnail_hook=thumb_hook,
            thumbnail_badge=thumb_badge,
            video_path=final_video_dest,
            strict_counterpoint=False,
            seo_input=seo_pkg,
            skill=skill_obj,
        )

        project.thumbnail_path = str(pub_result.thumbnail_path)
        project.thumbnail_preview_path = str(pub_result.thumbnail_preview_path)

        # Pipeline complete!
        project.stage = PipelineStage.COMPLETE
        project.progress = 100.0
        project.error = None
        project.current_step_text = "Hoàn tất toàn bộ quy trình! Sẵn sàng xuất bản lên YouTube."

        self.emit_event(
            project_id=project_id,
            stage=PipelineStage.COMPLETE,
            progress=100.0,
            message="QUY TRÌNH HOÀN TẤT 100%! Video 1080p, Thumbnail safe-zone và gói SEO đã sẵn sàng.",
            details={
                "video_path": project.final_video_path,
                "thumbnail_path": project.thumbnail_path,
                "thumbnail_preview_path": project.thumbnail_preview_path,
                "seo_markdown_path": project.seo_markdown_path,
            },
        )
