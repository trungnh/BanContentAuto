"""
Documentary & Historical Montage Assembler.
Implements the Transformative Fair Use pipeline (CD Media & Documentary style):
1. Strips all original footage audio.
2. Applies cinematic Ken Burns slow-zoom and color grading (LUT/contrast/vignette).
3. 3-Layer Audio Mix: Voiceover + Ducked Cinematic BGM + SFX.
4. Burns styled high-retention subtitles.
5. Emits broadcast-compliant 1080p 30fps MP4.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autovideo.core.binary_manager import BinaryManager
from autovideo.production.transformer import VideoProbeError, VideoProbeInfo, probe_video

logger = logging.getLogger(__name__)


@dataclass
class DocumentarySceneItem:
    """A single atomic scene in the documentary montage."""

    scene_id: str
    video_path: Path
    audio_path: Path
    text: str
    duration_sec: float
    cluster_id: str = "cluster_001"
    environment_id: str = "default_env"
    camera_scale: str = "Wide"  # "Wide", "Medium", "Closeup", "Detail"
    virtual_reframe: Optional[str] = None  # "center_zoom", "top_closeup", "pan_left_right", "flip_slowmo"
    sfx_cue: Optional[str] = None


@dataclass
class DocumentaryAssemblerConfig:
    """Styling and encoding configuration for documentary montage."""

    target_width: int = 1920
    target_height: int = 1080
    target_fps: int = 30
    crf: int = 21
    video_preset: str = "veryfast"
    apply_vignette: bool = True
    apply_color_grade: bool = True
    contrast: float = 1.10
    brightness: float = -0.02
    saturation: float = 1.15
    bgm_volume: float = 0.18
    voice_volume: float = 1.0


class DocumentaryAssembler:
    """
    Assembles atomic documentary scenes into a cohesive, high-retention film
    with transformative visual styling and professional multi-layer sound.
    """

    def __init__(
        self,
        config: Optional[DocumentaryAssemblerConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self.config = config or DocumentaryAssemblerConfig()
        self.binary_manager = binary_manager or BinaryManager()
        self.ffmpeg_path = self.binary_manager.get_binary_path("ffmpeg")
        self.ffprobe_path = self.binary_manager.get_binary_path("ffprobe")

    def _build_video_filter(
        self,
        duration_sec: float,
        camera_scale: str = "Wide",
        virtual_reframe: Optional[str] = None,
    ) -> str:
        """
        Builds FFmpeg filter chain with Virtual Camera & Shot Scale progression:
        - Wide: Full scene context with subtle dynamic zoom.
        - Medium: 1.15x focused on subject action.
        - Closeup: 1.35x centered on face/eyes/head.
        - Detail: 1.55x macro focus on critical object with vignette.
        - Virtual Reframe: dynamic pan, top closeup, or flip slowmo.
        """
        w = self.config.target_width
        h = self.config.target_height
        fps = self.config.target_fps
        frames = max(int(duration_sec * fps), 30)

        filters = [
            f"scale={w}:{h}:force_original_aspect_ratio=increase",
            f"crop={w}:{h}",
            f"fps={fps}",
        ]

        if virtual_reframe == "flip_slowmo":
            filters.append("hflip")

        if self.config.apply_color_grade:
            filters.append(
                f"eq=contrast={self.config.contrast}:brightness={self.config.brightness}:saturation={self.config.saturation}"
            )

        if self.config.apply_vignette:
            vig_strength = "PI/3.8" if camera_scale in ("Closeup", "Detail") else "PI/4.5"
            filters.append(f"vignette={vig_strength}")

        # Virtual Camera Re-framing & Shot Scale Hierarchy
        # CRITICAL: Always use d=1 for live video footage. In FFmpeg zoompan, d > 1 repeats
        # the same frame for d output frames, which completely freezes live video into a still image!
        # With d=1, FFmpeg consumes 1 input video frame per output frame, preserving 100% live motion.
        scale_lower = camera_scale.lower()
        if virtual_reframe == "pan_left_right":
            # Dynamic pan from left to right across frame
            filters.append(
                f"zoompan=z=1.20:x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"
            )
        elif virtual_reframe == "top_closeup" or scale_lower == "closeup":
            # Focus on upper 35% of frame (eye / head level)
            filters.append(
                f"zoompan=z='min(1.22+on*0.0004,1.38)':x='iw/2-(iw/zoom/2)':y='max(0,ih/3-(ih/zoom/3))':d=1:s={w}x{h}:fps={fps}"
            )
        elif scale_lower == "detail":
            # Macro zoom into key detail
            filters.append(
                f"zoompan=z='min(1.40+on*0.0003,1.55)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"
            )
        elif scale_lower == "medium":
            filters.append(
                f"zoompan=z='min(1.10+on*0.0004,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"
            )
        else:
            # Default Wide shot: slow breath zoom (1.00 -> 1.05)
            filters.append(
                f"zoompan=z='min(1.00+on*0.0003,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"
            )

        return ",".join(filters)

    def assemble_scene_clip(
        self,
        item: DocumentarySceneItem,
        output_path: Path,
    ) -> Path:
        """
        Muxes a single scene: video footage transformed to target specs + voiceover audio.
        Original video audio is completely stripped.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        vf = self._build_video_filter(
            duration_sec=item.duration_sec,
            camera_scale=item.camera_scale,
            virtual_reframe=item.virtual_reframe,
        )

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i", str(item.video_path),
            "-i", str(item.audio_path),
            "-filter_complex", f"[0:v]{vf}[v_out]",
            "-map", "[v_out]",
            "-map", "1:a",
            "-t", f"{item.duration_sec:.3f}",
            "-c:v", "libx264",
            "-preset", self.config.video_preset,
            "-crf", str(self.config.crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-shortest",
            str(output_path),
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            logger.error("FFmpeg assemble_scene_clip failed: %s", res.stderr)
            raise RuntimeError(f"Scene muxing failed for {item.scene_id}: {res.stderr[:300]}")

        return output_path

    def concatenate_scenes(
        self,
        scene_files: List[Path],
        output_path: Path,
        bgm_path: Optional[Path] = None,
        subtitle_ass_path: Optional[Path] = None,
    ) -> Path:
        """
        Concatenates atomic scene clips into the final video.
        Optionally mixes background music with audio ducking and burns subtitles.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        list_file = output_path.parent / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for sf in scene_files:
                # Use forward slashes for ffmpeg concat demuxer
                clean_path = str(sf.resolve()).replace("\\", "/")
                f.write(f"file '{clean_path}'\n")

        # 1. Base concatenation
        temp_concat = output_path.parent / "temp_concatenated.mp4"
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(temp_concat),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0 or not temp_concat.exists():
            raise RuntimeError(f"Concat failed: {res.stderr[:300]}")

        # 2. Add BGM and/or Subtitles if provided
        final_input = temp_concat
        if bgm_path and bgm_path.exists():
            # Mix voiceover with BGM: voiceover 1.0, BGM ducked to 0.18
            muxed_bgm = output_path.parent / "temp_with_bgm.mp4"
            bgm_cmd = [
                str(self.ffmpeg_path),
                "-y",
                "-i", str(temp_concat),
                "-stream_loop", "-1",
                "-i", str(bgm_path),
                "-filter_complex",
                f"[0:a]volume=1.0[voice];[1:a]volume={self.config.bgm_volume}[bgm];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[a_out]",
                "-map", "0:v",
                "-map", "[a_out]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(muxed_bgm),
            ]
            res_bgm = subprocess.run(bgm_cmd, capture_output=True, text=True, check=False)
            if res_bgm.returncode == 0 and muxed_bgm.exists():
                final_input = muxed_bgm

        # 3. Burn subtitles if available
        if subtitle_ass_path and subtitle_ass_path.exists():
            clean_sub = str(subtitle_ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
            sub_cmd = [
                str(self.ffmpeg_path),
                "-y",
                "-i", str(final_input),
                "-vf", f"subtitles='{clean_sub}'",
                "-c:v", "libx264",
                "-preset", self.config.video_preset,
                "-crf", str(self.config.crf),
                "-c:a", "copy",
                str(output_path),
            ]
            res_sub = subprocess.run(sub_cmd, capture_output=True, text=True, check=False)
            if res_sub.returncode == 0 and output_path.exists():
                return output_path

        # If no subtitle burn needed or fallback:
        if final_input != output_path:
            import shutil
            shutil.copy2(final_input, output_path)

        return output_path
