"""
Smart Video Scene Splitter and Vault Indexer.
Splits long video files (movies, series episodes, documentary footage from Bilibili/YouTube)
into atomic, reusable 3-6 second shots with stripped audio for Transformative Fair Use.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autovideo.core.binary_manager import BinaryManager
from autovideo.production.transformer import VideoProbeError, VideoProbeInfo, probe_video

logger = logging.getLogger(__name__)


@dataclass
class ShotInfo:
    """Metadata for an atomic extracted shot."""

    shot_id: str
    file_path: Path
    duration_sec: float
    width: int
    height: int
    thumbnail_path: Optional[Path] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "file_path": str(self.file_path),
            "duration_sec": round(self.duration_sec, 2),
            "width": self.width,
            "height": self.height,
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
            "tags": self.tags,
        }


class SceneSplitter:
    """
    Automated scene boundary detector and video shot extractor.
    Splits long footage into atomic shots (3.0s - 6.0s) suitable for documentary montage.
    """

    def __init__(self, binary_manager: Optional[BinaryManager] = None):
        self.binary_manager = binary_manager or BinaryManager()
        self.ffmpeg_path = self.binary_manager.get_binary_path("ffmpeg")
        self.ffprobe_path = self.binary_manager.get_binary_path("ffprobe")

    def detect_scene_changes(
        self,
        video_path: Path,
        threshold: float = 0.35,
        max_scan_sec: Optional[float] = None,
    ) -> List[float]:
        """
        Detect scene change cut points using FFmpeg's scene score filter.
        Returns sorted list of timestamps in seconds where scene cuts occur.
        """
        cmd = [
            str(self.ffmpeg_path),
            "-nostdin",
            "-hide_banner",
        ]
        if max_scan_sec:
            cmd.extend(["-t", str(max_scan_sec)])

        cmd.extend([
            "-i", str(video_path),
            "-filter:v", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null",
            "-",
        ])

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception as e:
            logger.warning("Scene change detection failed via FFmpeg: %s", e)
            return []

        pts_times: List[float] = []
        # showinfo prints lines like: [Parsed_showinfo_1 @ ...] n: ... pts_time:12.3456 ...
        pattern = re.compile(r"pts_time:([0-9\.]+)")
        for line in res.stderr.splitlines():
            if "pts_time:" in line:
                m = pattern.search(line)
                if m:
                    try:
                        t = float(m.group(1))
                        if t > 0.5:  # ignore 0s glitch
                            pts_times.append(t)
                    except ValueError:
                        continue

        pts_times.sort()
        # Deduplicate timestamps closer than 1.5 seconds
        filtered: List[float] = []
        for t in pts_times:
            if not filtered or (t - filtered[-1]) >= 1.5:
                filtered.append(t)

        return filtered

    def split_video(
        self,
        video_path: Path,
        output_dir: Path,
        min_duration: float = 2.5,
        max_duration: float = 6.5,
        scene_threshold: float = 0.35,
        max_scan_sec: Optional[float] = None,
        prefix: str = "shot",
        strip_audio: bool = True,
    ) -> List[ShotInfo]:
        """
        Splits video into individual atomic shot files.
        Guarantees duration within [min_duration, max_duration].
        Removes audio track by default to eliminate copyright / reused audio risks.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = probe_video(video_path, self.binary_manager)
        total_duration = max_scan_sec if max_scan_sec and max_scan_sec < probe.duration_sec else probe.duration_sec

        # 1. Detect natural scene change points
        cuts = self.detect_scene_changes(video_path, threshold=scene_threshold, max_scan_sec=total_duration)

        # 2. Build time intervals [start, end]
        timestamps = [0.0] + [c for c in cuts if c < total_duration] + [total_duration]
        intervals: List[Tuple[float, float]] = []

        for i in range(len(timestamps) - 1):
            start = timestamps[i]
            end = timestamps[i + 1]
            seg_len = end - start

            if seg_len < min_duration:
                # If too short, merge with previous or next if possible
                if intervals and (intervals[-1][1] - intervals[-1][0] + seg_len) <= max_duration:
                    prev_start, _ = intervals.pop()
                    intervals.append((prev_start, end))
                else:
                    intervals.append((start, end))
            elif seg_len > max_duration:
                # If too long, sub-divide into chunks of ~4.0s
                sub_chunks = int(seg_len // 4.0) + 1
                step = seg_len / sub_chunks
                for c in range(sub_chunks):
                    sub_start = start + c * step
                    sub_end = min(sub_start + step, end)
                    if sub_end - sub_start >= 1.5:
                        intervals.append((sub_start, sub_end))
            else:
                intervals.append((start, end))

        # 3. Extract each shot using FFmpeg
        shots: List[ShotInfo] = []
        for idx, (start_t, end_t) in enumerate(intervals, 1):
            dur = end_t - start_t
            if dur < 1.0:
                continue

            shot_id = f"{prefix}_{idx:03d}"
            out_file = output_dir / f"{shot_id}.mp4"
            thumb_file = output_dir / f"{shot_id}.jpg"

            cmd = [
                str(self.ffmpeg_path),
                "-y",
                "-ss", f"{start_t:.3f}",
                "-i", str(video_path),
                "-t", f"{dur:.3f}",
            ]
            if strip_audio:
                cmd.append("-an")  # Strip audio completely for transformative Fair Use

            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                str(out_file),
            ])

            res = subprocess.run(cmd, capture_output=True, check=False)
            if res.returncode == 0 and out_file.exists():
                # Extract thumbnail at midpoint of shot
                thumb_t = start_t + (dur / 2.0)
                thumb_cmd = [
                    str(self.ffmpeg_path),
                    "-y",
                    "-ss", f"{thumb_t:.3f}",
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "3",
                    str(thumb_file),
                ]
                subprocess.run(thumb_cmd, capture_output=True, check=False)

                shots.append(
                    ShotInfo(
                        shot_id=shot_id,
                        file_path=out_file,
                        duration_sec=dur,
                        width=probe.width,
                        height=probe.height,
                        thumbnail_path=thumb_file if thumb_file.exists() else None,
                    )
                )

        # 4. Save manifest
        manifest_file = output_dir / "shots_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in shots], f, ensure_ascii=False, indent=2)

        logger.info("Split %s into %d atomic shots in %s", video_path.name, len(shots), output_dir)
        return shots
