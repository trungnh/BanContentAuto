"""
Rolling Disk Buffer Manager (WU-06, REQ-B3-01, NFR-PERF-01).
Monitors intermediate scene cache directories and provides proactive and reactive
buffer cleanup to keep disk consumption strictly <= 3-5 GB during long-form video renders.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set

from autovideo.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)

BYTES_PER_GB = 1024 * 1024 * 1024


class RollingDiskBuffer:
    """
    Manages and bounds disk cache usage for temporary atomic scenes.
    Ensures that once a Chapter is assembled into a part file, intermediate
    atomic scene files are promptly deleted to prevent disk overflow.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        max_buffer_gb: Optional[float] = None,
        buffer_dir: Optional[Path | str] = None,
    ):
        self._config = config or get_config()
        self._max_buffer_gb = (
            max_buffer_gb
            if max_buffer_gb is not None
            else self._config.performance.rolling_buffer_max_gb
        )
        self._buffer_dir = (
            Path(buffer_dir).resolve()
            if buffer_dir is not None
            else self._config.paths.cache_temp_scenes_dir.resolve()
        )
        self._buffer_dir.mkdir(parents=True, exist_ok=True)

        self._peak_bytes: int = 0
        self._total_freed_bytes: int = 0
        self._total_files_deleted: int = 0

    @property
    def buffer_dir(self) -> Path:
        """The monitored root buffer directory."""
        return self._buffer_dir

    @property
    def max_buffer_gb(self) -> float:
        """Maximum allowable buffer size in Gigabytes."""
        return self._max_buffer_gb

    @property
    def max_buffer_bytes(self) -> int:
        """Maximum allowable buffer size in Bytes."""
        return int(self._max_buffer_gb * BYTES_PER_GB)

    def get_buffer_size_bytes(self, target_dir: Optional[Path | str] = None) -> int:
        """
        Recursively calculates the total disk size in bytes of files in the target directory.
        Defaults to the configured buffer directory.
        """
        root = Path(target_dir).resolve() if target_dir is not None else self._buffer_dir
        if not root.exists():
            return 0

        total_bytes = 0
        try:
            for entry in root.rglob("*"):
                if entry.is_file():
                    try:
                        total_bytes += entry.stat().st_size
                    except (OSError, FileNotFoundError):
                        # File may have been removed concurrently
                        continue
        except OSError as e:
            logger.warning(f"Error scanning buffer directory {root}: {e}")

        if total_bytes > self._peak_bytes:
            self._peak_bytes = total_bytes

        return total_bytes

    def measure_directory_bytes(self, target_dir: Optional[Path | str] = None) -> int:
        """
        Recursively calculates total bytes in directory (alias for get_buffer_size_bytes).
        """
        return self.get_buffer_size_bytes(target_dir)

    def get_buffer_size_gb(self, target_dir: Optional[Path | str] = None) -> float:
        """Calculates total disk size in Gigabytes."""
        return self.get_buffer_size_bytes(target_dir) / BYTES_PER_GB

    def is_buffer_safe(self, target_dir: Optional[Path | str] = None) -> bool:
        """
        Returns True if current buffer usage is strictly within the allowed limit.
        """
        return self.get_buffer_size_bytes(target_dir) <= self.max_buffer_bytes

    def cleanup_files(self, file_paths: Iterable[Path | str]) -> int:
        """
        Removes the specified collection of files from disk.
        Returns the number of files successfully deleted.
        """
        deleted_count = 0
        freed_bytes = 0

        for item in file_paths:
            path = Path(item).resolve()
            if path.is_file():
                try:
                    file_size = path.stat().st_size
                    path.unlink()
                    freed_bytes += file_size
                    deleted_count += 1
                    logger.debug(f"RollingBuffer: Deleted temp file {path} ({file_size} bytes)")
                except (OSError, FileNotFoundError) as e:
                    logger.warning(f"RollingBuffer: Failed to delete {path}: {e}")

        self._total_freed_bytes += freed_bytes
        self._total_files_deleted += deleted_count
        return deleted_count

    def cleanup_chapter_scenes(
        self,
        project_id: str,
        scene_paths: Sequence[Path | str],
    ) -> int:
        """
        Deletes all atomic scene files belonging to a completed chapter.
        This enforces the Rolling Disk Buffer invariant immediately after
        each chapter is successfully rendered into a part file.
        """
        logger.info(
            f"RollingBuffer: Cleaning up {len(scene_paths)} atomic scene files for project {project_id}"
        )
        return self.cleanup_files(scene_paths)

    def enforce_buffer_limit(
        self,
        protected_paths: Optional[Set[Path]] = None,
        target_dir: Optional[Path | str] = None,
    ) -> int:
        """
        Proactively purges the oldest intermediate temporary files in the buffer directory
        if the total usage exceeds `max_buffer_gb`. Files in `protected_paths` are preserved.
        Returns the number of purged files.
        """
        root = Path(target_dir).resolve() if target_dir is not None else self._buffer_dir
        if not root.exists():
            return 0

        current_size = self.get_buffer_size_bytes(root)
        if current_size <= self.max_buffer_bytes:
            return 0

        protected = {p.resolve() for p in protected_paths} if protected_paths else set()
        logger.warning(
            f"RollingBuffer: Usage {current_size / BYTES_PER_GB:.2f} GB exceeds limit "
            f"{self._max_buffer_gb:.2f} GB. Initiating emergency rolling purge."
        )

        # Collect candidate files sorted by modification time (oldest first)
        candidates = []
        for entry in root.rglob("*"):
            if entry.is_file() and entry.resolve() not in protected:
                try:
                    candidates.append((entry.stat().st_mtime, entry))
                except (OSError, FileNotFoundError):
                    continue

        candidates.sort(key=lambda x: x[0])

        purged_count = 0
        for _, file_path in candidates:
            if self.get_buffer_size_bytes(root) <= self.max_buffer_bytes:
                break
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                self._total_freed_bytes += size
                purged_count += 1
            except (OSError, FileNotFoundError):
                continue

        return purged_count

    def get_metrics(self) -> Dict[str, object]:
        """Returns diagnostic and performance metrics of the buffer."""
        current_bytes = self.get_buffer_size_bytes()
        return {
            "current_bytes": current_bytes,
            "current_gb": round(current_bytes / BYTES_PER_GB, 4),
            "max_buffer_gb": self._max_buffer_gb,
            "peak_bytes": self._peak_bytes,
            "peak_gb": round(self._peak_bytes / BYTES_PER_GB, 4),
            "total_freed_bytes": self._total_freed_bytes,
            "total_freed_gb": round(self._total_freed_bytes / BYTES_PER_GB, 4),
            "total_files_deleted": self._total_files_deleted,
            "is_safe": self.is_buffer_safe(),
        }
