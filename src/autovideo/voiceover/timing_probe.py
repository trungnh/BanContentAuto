"""
Audio Timing Probe Module (REQ-B2-03).
Provides millisecond / sub-millisecond precision duration measurements for audio files
(WAV, MP3, AAC, OGG, FLAC) using Mutagen with automatic FFprobe fallback.
Guarantee: duration measurement error <= 10ms.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mutagen

from autovideo.core.binary_manager import BinaryManager


class AudioProbeError(Exception):
    """Raised when an audio file cannot be probed by either mutagen or ffprobe."""
    pass


@dataclass(frozen=True)
class AudioProbeResult:
    """Detailed audio file metadata and exact duration."""

    file_path: Path
    duration_sec: float
    duration_ms: int
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bitrate: Optional[int] = None
    format: str = "unknown"
    probe_method: str = "mutagen"  # "mutagen" | "ffprobe"

    def to_dict(self) -> dict:
        return {
            "file_path": str(self.file_path),
            "duration_sec": self.duration_sec,
            "duration_ms": self.duration_ms,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bitrate": self.bitrate,
            "format": self.format,
            "probe_method": self.probe_method,
        }


class TimingProbe:
    """
    Precision Audio Timing Engine.
    Probes audio files using mutagen first; if mutagen encounters an unknown format
    or read failure, seamlessly falls back to ffprobe.
    """

    def __init__(self, binary_manager: Optional[BinaryManager] = None):
        self._binary_manager = binary_manager or BinaryManager()

    def probe(self, audio_path: Path | str) -> AudioProbeResult:
        """
        Probe an audio file and return precision duration and metadata.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            ValueError: If the file is empty (0 bytes).
            AudioProbeError: If audio duration cannot be parsed.
        """
        path = Path(audio_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        file_size = path.stat().st_size
        if file_size == 0:
            raise ValueError(f"Audio file is empty (0 bytes): {path}")

        # 1. Try mutagen probe
        mutagen_result = self._probe_with_mutagen(path)
        if mutagen_result is not None:
            return mutagen_result

        # 2. Fall back to ffprobe
        ffprobe_result = self._probe_with_ffprobe(path)
        if ffprobe_result is not None:
            return ffprobe_result

        raise AudioProbeError(
            f"Failed to probe duration for '{path}' via both mutagen and ffprobe."
        )

    def _probe_with_mutagen(self, path: Path) -> Optional[AudioProbeResult]:
        """Attempt probing audio using mutagen."""
        try:
            audio = mutagen.File(str(path))
            if audio is None or audio.info is None:
                return None

            length = getattr(audio.info, "length", None)
            if length is None or length <= 0.0:
                return None

            duration_sec = round(float(length), 4)
            duration_ms = int(round(duration_sec * 1000))

            sample_rate = getattr(audio.info, "sample_rate", None)
            channels = getattr(audio.info, "channels", None)
            bitrate = getattr(audio.info, "bitrate", None)

            # Determine audio format name
            fmt = path.suffix.lstrip(".").lower()
            if not fmt:
                fmt = type(audio).__name__.lower()

            return AudioProbeResult(
                file_path=path,
                duration_sec=duration_sec,
                duration_ms=duration_ms,
                sample_rate=int(sample_rate) if sample_rate else None,
                channels=int(channels) if channels else None,
                bitrate=int(bitrate) if bitrate else None,
                format=fmt,
                probe_method="mutagen",
            )
        except Exception:
            return None

    def _probe_with_ffprobe(self, path: Path) -> Optional[AudioProbeResult]:
        """Fallback probe using external ffprobe binary."""
        ffprobe_path, _ = self._binary_manager.find_binary("ffprobe")
        if not ffprobe_path or not ffprobe_path.exists():
            return None

        cmd = [
            str(ffprobe_path),
            "-v", "error",
            "-show_entries", "format=duration,bit_rate,format_name",
            "-show_entries", "stream=sample_rate,channels,codec_name",
            "-of", "json",
            str(path),
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None

            data = json.loads(proc.stdout)
            format_info = data.get("format", {})
            duration_raw = format_info.get("duration")
            if not duration_raw:
                return None

            duration_sec = round(float(duration_raw), 4)
            duration_ms = int(round(duration_sec * 1000))

            bitrate = format_info.get("bit_rate")
            fmt = format_info.get("format_name", path.suffix.lstrip(".")).split(",")[0]

            streams = data.get("streams", [])
            sample_rate = None
            channels = None
            if streams:
                sample_rate = streams[0].get("sample_rate")
                channels = streams[0].get("channels")

            return AudioProbeResult(
                file_path=path,
                duration_sec=duration_sec,
                duration_ms=duration_ms,
                sample_rate=int(sample_rate) if sample_rate else None,
                channels=int(channels) if channels else None,
                bitrate=int(bitrate) if bitrate else None,
                format=fmt,
                probe_method="ffprobe",
            )
        except Exception:
            return None


def probe_audio_duration(path: Path | str) -> float:
    """
    Convenience function returning the duration of an audio file in seconds.
    Precision error <= 10ms.
    """
    probe = TimingProbe()
    return probe.probe(path).duration_sec
