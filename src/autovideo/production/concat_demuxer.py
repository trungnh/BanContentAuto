"""
Fast Concat Demuxer Engine (WU-06, REQ-B3-02, NFR-COMP-01).
Performs zero-reencode joining of standardized MP4 parts using FFmpeg concat demuxer:
`ffmpeg -f concat -safe 0 -i concat_list.txt -c copy -y output_path`.
Achieves joining 20-30 minute long-form videos in under 40 seconds.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.production.transformer import VideoProbeInfo, probe_video

logger = logging.getLogger(__name__)


class ConcatDemuxerError(RuntimeError):
    """Raised when concat demuxer execution or verification fails."""
    pass


@dataclass(frozen=True)
class ConcatResult:
    """Detailed result of a zero-reencode concatenation operation."""

    output_path: Path
    input_count: int
    duration_sec: float
    width: int
    height: int
    fps: float
    has_audio: bool
    elapsed_time_sec: float
    intermediate_cleaned: bool


class ConcatDemuxer:
    """
    Executes lightning-fast Zero-Reencode video concatenation using
    the FFmpeg Concat Demuxer.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self._config = config or get_config()
        self._binary_manager = binary_manager or BinaryManager()

    def generate_concat_manifest(
        self,
        file_paths: Sequence[Path | str],
        manifest_path: Optional[Path | str] = None,
    ) -> Path:
        """
        Creates an FFmpeg concat demuxer formatted text manifest file.
        Format per line: file 'path/to/part.mp4' with proper escaping.
        """
        if not file_paths:
            raise ValueError("file_paths cannot be empty for concat manifest")

        resolved_paths: List[Path] = []
        for p in file_paths:
            resolved = Path(p).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Part file not found: {resolved}")
            if resolved.stat().st_size == 0:
                raise ValueError(f"Part file is empty: {resolved}")
            resolved_paths.append(resolved)

        if manifest_path is None:
            # Create a temp file
            fd, tmp_file = tempfile.mkstemp(prefix="concat_manifest_", suffix=".txt")
            import os
            os.close(fd)
            manifest = Path(tmp_file)
        else:
            manifest = Path(manifest_path).resolve()
            manifest.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        for p in resolved_paths:
            # FFmpeg concat demuxer syntax requires forward slashes on Windows
            # and escaping of single quotes as '\''.
            posix_str = p.as_posix().replace("'", "'\\''")
            lines.append(f"file '{posix_str}'\n")

        manifest.write_text("".join(lines), encoding="utf-8")
        return manifest

    def concat(
        self,
        input_paths: Sequence[Path | str],
        output_path: Path | str,
        clean_intermediate_parts: Optional[bool] = None,
        duration_tolerance_sec: float = 2.0,
    ) -> ConcatResult:
        """
        Joins all provided input MP4 parts into `output_path` using `-c copy`.
        Verifies the resulting video integrity using ffprobe.
        Optionally purges input parts when `clean_intermediate_parts` is True.
        """
        if not input_paths:
            raise ValueError("input_paths cannot be empty")

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        should_clean = (
            clean_intermediate_parts
            if clean_intermediate_parts is not None
            else self._config.performance.clean_intermediate_parts
        )

        # 1. Generate concat manifest
        manifest_path = self.generate_concat_manifest(input_paths)

        # 2. Prepare FFmpeg command
        ffmpeg_bin = self._binary_manager.require("ffmpeg").path
        cmd = [
            str(ffmpeg_bin),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(manifest_path),
            "-c", "copy",
            str(out),
        ]

        logger.info(f"ConcatDemuxer: Merging {len(input_paths)} files into {out}")
        start_time = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as e:
            raise ConcatDemuxerError(f"Concat demuxer timed out after 120s: {e}") from e
        finally:
            # Clean up the temporary manifest file
            try:
                if manifest_path.exists():
                    manifest_path.unlink()
            except OSError:
                pass

        elapsed_sec = time.monotonic() - start_time

        if proc.returncode != 0:
            raise ConcatDemuxerError(
                f"FFmpeg concat demuxer failed with exit code {proc.returncode}: {proc.stderr}"
            )

        if not out.exists() or out.stat().st_size == 0:
            raise ConcatDemuxerError(f"Concat output file was not created or is empty: {out}")

        # 3. Post-verification of output integrity via ffprobe
        probe = probe_video(out, binary_manager=self._binary_manager)

        if not probe.has_audio:
            logger.warning(f"ConcatDemuxer: Output video {out} has no detected audio stream.")

        # 4. Clean intermediate parts if requested
        intermediate_cleaned = False
        if should_clean:
            logger.info("ConcatDemuxer: Purging intermediate input parts as configured.")
            for p in input_paths:
                try:
                    p_path = Path(p).resolve()
                    # Do not delete the output file if by mistake included
                    if p_path != out and p_path.is_file():
                        p_path.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete intermediate part {p}: {e}")
            intermediate_cleaned = True

        logger.info(
            f"ConcatDemuxer: Successfully assembled {out.name} ({probe.duration_sec:.2f}s, "
            f"{probe.width}x{probe.height}) in {elapsed_sec:.2f}s (Zero Re-encode)"
        )

        return ConcatResult(
            output_path=out,
            input_count=len(input_paths),
            duration_sec=probe.duration_sec,
            width=probe.width,
            height=probe.height,
            fps=probe.fps,
            has_audio=probe.has_audio,
            elapsed_time_sec=elapsed_sec,
            intermediate_cleaned=intermediate_cleaned,
        )
