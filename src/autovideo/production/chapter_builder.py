"""
Modular Chapter Builder & Production Pipeline (WU-06, REQ-B3-01, NFR-REL-01, VAC-UI-02).
Coordinates the rendering of atomic scenes per chapter, merges them into intermediate
part_XX.mp4 files, triggers immediate rolling buffer cleanup, and maintains fault-tolerant
checkpoint state (state.json) for crash recovery via `--resume`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.production.concat_demuxer import ConcatDemuxer, ConcatResult
from autovideo.production.rolling_buffer import RollingDiskBuffer
from autovideo.production.scene_muxer import SceneMuxConfig, SceneMuxResult, SceneMuxer
from autovideo.production.transformer import TransformationConfig, probe_video
from autovideo.script.pipeline import Chapter, Scene, Screenplay

logger = logging.getLogger(__name__)


class ChapterBuilderError(RuntimeError):
    """Raised when chapter rendering or pipeline orchestration fails."""
    pass


@dataclass
class SceneAssets:
    """Asset bundle required to assemble one atomic scene."""

    media_path: Path | str
    audio_path: Optional[Path | str] = None
    ambient_path: Optional[Path | str] = None
    transform_config: Optional[TransformationConfig] = None
    start_offset_sec: float = 0.0
    is_preassembled: bool = False


@dataclass
class ChapterRenderResult:
    """Result metadata of an assembled chapter part."""

    chapter_index: int
    title: str
    part_path: Path
    duration_sec: float
    scene_count: int
    skipped_from_cache: bool = False


@dataclass
class PipelineCheckpoint:
    """Persistent state tracking for fault-tolerant crash recovery (NFR-REL-01)."""

    project_id: str
    status: str = "in_progress"  # in_progress | completed | failed
    completed_chapters: List[int] = field(default_factory=list)
    chapter_parts: Dict[str, str] = field(default_factory=dict)
    final_video: Optional[str] = None
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def save(self, file_path: Path | str) -> None:
        """Persists checkpoint state to disk atomically."""
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.last_updated = datetime.now(timezone.utc).isoformat()
        
        # Write to temp file then rename for atomic durability
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        if path.exists():
            path.unlink()
        tmp_path.rename(path)

    @classmethod
    def load(cls, file_path: Path | str) -> Optional[PipelineCheckpoint]:
        """Loads existing checkpoint state from disk if present."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                project_id=data.get("project_id", ""),
                status=data.get("status", "in_progress"),
                completed_chapters=data.get("completed_chapters", []),
                chapter_parts=data.get("chapter_parts", {}),
                final_video=data.get("final_video"),
                last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            )
        except Exception as e:
            logger.warning(f"Failed to read checkpoint file {path}: {e}")
            return None


class ChapterBuilder:
    """
    Builds long-form video chapters modularly.
    Renders atomic scenes -> merges into part_{idx:02d}.mp4 -> triggers rolling buffer cleanup.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        scene_muxer: Optional[SceneMuxer] = None,
        concat_demuxer: Optional[ConcatDemuxer] = None,
        rolling_buffer: Optional[RollingDiskBuffer] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self._config = config or get_config()
        self._binary_manager = binary_manager or BinaryManager()
        self._scene_muxer = scene_muxer or SceneMuxer(
            config=self._config, binary_manager=self._binary_manager
        )
        self._concat_demuxer = concat_demuxer or ConcatDemuxer(
            config=self._config, binary_manager=self._binary_manager
        )
        self._rolling_buffer = rolling_buffer or RollingDiskBuffer(
            config=self._config
        )

    @property
    def rolling_buffer(self) -> RollingDiskBuffer:
        return self._rolling_buffer

    @property
    def concat_demuxer(self) -> ConcatDemuxer:
        return self._concat_demuxer

    def is_chapter_part_valid(self, part_path: Path | str) -> bool:
        """Verifies that an existing chapter part file is valid and readable."""
        path = Path(part_path).resolve()
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            probe = probe_video(path, binary_manager=self._binary_manager)
            return probe.duration_sec > 0 and probe.width > 0 and probe.height > 0
        except Exception:
            return False

    def build_chapter(
        self,
        project_id: str,
        chapter: Chapter,
        asset_resolver: Union[
            Callable[[Scene], SceneAssets],
            Dict[str, SceneAssets],
        ],
        parts_dir: Optional[Path | str] = None,
        resume: bool = True,
        checkpoint: Optional[PipelineCheckpoint] = None,
    ) -> ChapterRenderResult:
        """
        Builds a single chapter:
        1. Checks if chapter is already completed (via resume & checkpoint).
        2. If not, assembles all atomic scenes in chapter.
        3. Merges atomic scenes into part_{idx:02d}.mp4 using ConcatDemuxer.
        4. Triggers Rolling Buffer to immediately delete atomic scene MP4 files.
        5. Updates checkpoint state.
        """
        parts_dir_path = (
            Path(parts_dir).resolve()
            if parts_dir is not None
            else (self._config.paths.get_project_render_dir(project_id) / "parts").resolve()
        )
        parts_dir_path.mkdir(parents=True, exist_ok=True)
        part_output_path = parts_dir_path / f"part_{chapter.chapter_index:02d}.mp4"

        # Checkpoint / Resume check
        if resume:
            is_in_checkpoint = (
                checkpoint is not None
                and chapter.chapter_index in checkpoint.completed_chapters
            )
            if (is_in_checkpoint or part_output_path.exists()) and self.is_chapter_part_valid(part_output_path):
                logger.info(
                    f"ChapterBuilder: Chapter {chapter.chapter_index} ({chapter.title}) already rendered and valid. Skipping (Resume)."
                )
                probe = probe_video(part_output_path, binary_manager=self._binary_manager)
                return ChapterRenderResult(
                    chapter_index=chapter.chapter_index,
                    title=chapter.title,
                    part_path=part_output_path,
                    duration_sec=probe.duration_sec,
                    scene_count=len(chapter.scenes),
                    skipped_from_cache=True,
                )

        logger.info(
            f"ChapterBuilder: Rendering Chapter {chapter.chapter_index} '{chapter.title}' ({len(chapter.scenes)} scenes)..."
        )

        # Assemble atomic scenes
        atomic_scene_paths: List[Path] = []
        temp_dir = self._config.paths.cache_temp_scenes_dir / project_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        for idx, scene in enumerate(chapter.scenes, start=1):
            if callable(asset_resolver):
                assets = asset_resolver(scene)
            elif isinstance(asset_resolver, dict):
                assets = asset_resolver.get(scene.scene_id)
                if assets is None:
                    raise ChapterBuilderError(
                        f"Missing assets for scene {scene.scene_id} in asset_resolver dictionary"
                    )
            else:
                raise TypeError("asset_resolver must be a callable or dict")

            scene_output = temp_dir / f"scene_{chapter.chapter_index:02d}_{idx:03d}.mp4"

            # If atomic scene was already assembled in B2 with video + audio + safe start_offset,
            # copy it directly to scene_output so Rolling Buffer can safely clean scene_output
            # after chapter assembly without touching the original preview scene file!
            if getattr(assets, "is_preassembled", False) and Path(assets.media_path).is_file():
                shutil.copyfile(assets.media_path, scene_output)
                atomic_scene_paths.append(scene_output)
                continue

            # Render atomic scene via SceneMuxer
            mux_result = self._scene_muxer.assemble_scene(
                project_id=project_id,
                scene_idx=idx,
                media_path=assets.media_path,
                voiceover_audio_path=assets.audio_path,
                ambient_audio_path=assets.ambient_path,
                target_duration_sec=scene.duration_sec if scene.duration_sec > 0 else None,
                start_offset_sec=getattr(assets, "start_offset_sec", 0.0),
                transform_config=assets.transform_config,
                output_path=scene_output,
            )
            atomic_scene_paths.append(mux_result.output_path)

        if not atomic_scene_paths:
            raise ChapterBuilderError(
                f"Chapter {chapter.chapter_index} contains no scenes to assemble"
            )

        # Merge atomic scenes into Chapter Part using ConcatDemuxer (-c copy)
        logger.info(
            f"ChapterBuilder: Merging {len(atomic_scene_paths)} atomic scenes into {part_output_path.name}"
        )
        concat_result = self._concat_demuxer.concat(
            input_paths=atomic_scene_paths,
            output_path=part_output_path,
            clean_intermediate_parts=False,  # We delegate cleanup to Rolling Buffer
        )

        # Immediate Rolling Disk Buffer cleanup (REQ-B3-01)
        self._rolling_buffer.cleanup_chapter_scenes(
            project_id=project_id,
            scene_paths=atomic_scene_paths,
        )

        # Update checkpoint if provided
        if checkpoint is not None:
            if chapter.chapter_index not in checkpoint.completed_chapters:
                checkpoint.completed_chapters.append(chapter.chapter_index)
            checkpoint.chapter_parts[str(chapter.chapter_index)] = str(part_output_path)
            state_file = self._config.paths.get_project_render_dir(project_id) / "state.json"
            checkpoint.save(state_file)

        return ChapterRenderResult(
            chapter_index=chapter.chapter_index,
            title=chapter.title,
            part_path=part_output_path,
            duration_sec=concat_result.duration_sec,
            scene_count=len(chapter.scenes),
            skipped_from_cache=False,
        )


@dataclass
class ProductionResult:
    """Comprehensive production pipeline execution result."""

    project_id: str
    final_video_path: Path
    total_duration_sec: float
    width: int
    height: int
    fps: float
    chapter_results: List[ChapterRenderResult]
    concat_elapsed_sec: float
    total_elapsed_sec: float
    resumed_chapters_count: int
    buffer_metrics: Dict[str, object]


class ProductionPipeline:
    """
    Unified end-to-end B3 Production Coordinator.
    Drives Screenplay -> Rolling Chapter Builder -> Concat Demuxer -> Final Video.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        chapter_builder: Optional[ChapterBuilder] = None,
        concat_demuxer: Optional[ConcatDemuxer] = None,
        rolling_buffer: Optional[RollingDiskBuffer] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self._config = config or get_config()
        self._binary_manager = binary_manager or BinaryManager()
        self._rolling_buffer = rolling_buffer or RollingDiskBuffer(config=self._config)
        self._concat_demuxer = concat_demuxer or ConcatDemuxer(
            config=self._config, binary_manager=self._binary_manager
        )
        self._chapter_builder = chapter_builder or ChapterBuilder(
            config=self._config,
            concat_demuxer=self._concat_demuxer,
            rolling_buffer=self._rolling_buffer,
            binary_manager=self._binary_manager,
        )

    def run(
        self,
        project_id: str,
        screenplay: Screenplay,
        asset_resolver: Union[
            Callable[[Scene], SceneAssets],
            Dict[str, SceneAssets],
        ],
        output_video_path: Optional[Path | str] = None,
        resume: bool = True,
        clean_intermediate_parts: Optional[bool] = None,
    ) -> ProductionResult:
        """
        Executes the entire B3 production pipeline:
        1. Initializes or loads checkpoint state.json.
        2. Iterates sequentially through chapters in the Screenplay.
        3. Renders each chapter with rolling buffer cleanup.
        4. Merges all part_XX.mp4 files into final video via Concat Demuxer (-c copy).
        5. Updates checkpoint to 'completed'.
        """
        start_time = time.monotonic()
        render_dir = self._config.paths.get_project_render_dir(project_id)
        render_dir.mkdir(parents=True, exist_ok=True)
        parts_dir = render_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)

        state_file = render_dir / "state.json"
        checkpoint = PipelineCheckpoint.load(state_file) if resume else None
        if checkpoint is None:
            checkpoint = PipelineCheckpoint(project_id=project_id)
            checkpoint.save(state_file)

        final_out = (
            Path(output_video_path).resolve()
            if output_video_path is not None
            else (render_dir / "final_video.mp4").resolve()
        )

        chapter_results: List[ChapterRenderResult] = []
        resumed_count = 0

        # Build each chapter sequentially
        for chapter in screenplay.chapters:
            result = self._chapter_builder.build_chapter(
                project_id=project_id,
                chapter=chapter,
                asset_resolver=asset_resolver,
                parts_dir=parts_dir,
                resume=resume,
                checkpoint=checkpoint,
            )
            chapter_results.append(result)
            if result.skipped_from_cache:
                resumed_count += 1

        # Check all part files exist
        part_paths = [cr.part_path for cr in chapter_results]
        for p in part_paths:
            if not p.is_file():
                raise ChapterBuilderError(f"Expected part file does not exist: {p}")

        # Concatenate all parts into Final Video using Concat Demuxer (Zero Re-encode)
        logger.info(
            f"ProductionPipeline: Concatenating {len(part_paths)} chapter parts into {final_out}"
        )
        concat_result = self._concat_demuxer.concat(
            input_paths=part_paths,
            output_path=final_out,
            clean_intermediate_parts=clean_intermediate_parts,
        )

        # Finalize checkpoint state
        checkpoint.status = "completed"
        checkpoint.final_video = str(final_out)
        checkpoint.save(state_file)

        total_elapsed = time.monotonic() - start_time
        metrics = self._rolling_buffer.get_metrics()

        logger.info(
            f"ProductionPipeline: Complete! Final video at {final_out} "
            f"({concat_result.duration_sec:.2f}s) produced in {total_elapsed:.2f}s "
            f"(Concat took {concat_result.elapsed_time_sec:.2f}s). Resumed: {resumed_count} chapters."
        )

        return ProductionResult(
            project_id=project_id,
            final_video_path=final_out,
            total_duration_sec=concat_result.duration_sec,
            width=concat_result.width,
            height=concat_result.height,
            fps=concat_result.fps,
            chapter_results=chapter_results,
            concat_elapsed_sec=concat_result.elapsed_time_sec,
            total_elapsed_sec=total_elapsed,
            resumed_chapters_count=resumed_count,
            buffer_metrics=metrics,
        )
