"""
Scene Muxer & Atomic Scene Assembly (WU-05, REQ-B2-04, VAC-UI-03).
Muxes transformed 16:9 video footage with sub-millisecond voiceover audio and ambient SFX.
Outputs standardized, broadcast-compliant atomic scenes (1080p, 30fps CFR, H.264 High@L4.1, AAC 192k).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.production.transformer import (
    TimingFitDecision,
    TransformationConfig,
    VideoProbeError,
    VideoProbeInfo,
    VideoTransformError,
    VideoTransformer,
    detect_crop_region,
    probe_video,
)
from autovideo.voiceover.timing_probe import TimingProbe


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


@dataclass
class SceneMuxConfig:
    """Standardized output codec settings for atomic scenes (NFR-COMP-01)."""

    video_codec: str = "libx264"
    video_preset: str = "veryfast"
    video_profile: str = "high"
    video_level: str = "4.1"
    video_pix_fmt: str = "yuv420p"
    video_fps: int = 30
    video_width: int = 1920
    video_height: int = 1080
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48000
    ambient_volume: float = 0.35  # 30-40% volume under voiceover
    voiceover_volume: float = 1.0


@dataclass(frozen=True)
class SceneMuxResult:
    """Metadata of an assembled atomic scene."""

    scene_id: int
    project_id: str
    output_path: Path
    duration_sec: float
    width: int
    height: int
    fps: float
    has_audio: bool
    timing_action: str


class SceneMuxer:
    """
    Assembles atomic scenes by orchestrating video transformation,
    timing adjustment, and multi-track audio blending.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        mux_config: Optional[SceneMuxConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self._app_config = config or get_config()
        self._mux_config = mux_config or SceneMuxConfig()
        self._binary_manager = binary_manager or BinaryManager()
        self._timing_probe = TimingProbe(binary_manager=self._binary_manager)

    def assemble_scene(
        self,
        project_id: str,
        scene_idx: int,
        media_path: Path | str,
        voiceover_audio_path: Path | str,
        ambient_audio_path: Optional[Path | str] = None,
        target_duration_sec: Optional[float] = None,
        start_offset_sec: float = 0.0,
        transform_config: Optional[TransformationConfig] = None,
        output_path: Optional[Path | str] = None,
    ) -> SceneMuxResult:
        """
        Assemble one atomic scene:
        1. Measure precise voiceover duration if not provided.
        2. Probe media geometry (aspect ratio, duration).
        3. Calculate timing fitting (trim, slow-motion, loop, image still).
        4. Generate FFmpeg filter graph (blurred margin, slow-motion, audio amix).
        5. Encode to uniform 1920x1080 @ 30fps H.264/AAC MP4.
        """
        media_p = Path(media_path).resolve()
        if not media_p.exists():
            raise FileNotFoundError(f"Media file not found: {media_p}")

        vo_p = Path(voiceover_audio_path).resolve()
        if not vo_p.exists():
            raise FileNotFoundError(f"Voiceover audio file not found: {vo_p}")

        # 1. Determine target duration from voiceover audio
        if target_duration_sec is None or target_duration_sec <= 0.0:
            vo_probe = self._timing_probe.probe(vo_p)
            duration = vo_probe.duration_sec
        else:
            duration = float(target_duration_sec)

        # 2. Probe media characteristics
        is_image = media_p.suffix.lower() in IMAGE_EXTENSIONS
        source_duration = 0.0
        source_is_vertical = False

        if not is_image:
            try:
                probe_info = probe_video(media_p, binary_manager=self._binary_manager)
                source_duration = probe_info.duration_sec
                source_is_vertical = probe_info.is_vertical
            except VideoProbeError as probe_err:
                if media_p.suffix.lower() in IMAGE_EXTENSIONS:
                    source_duration = 0.0
                    is_image = True
                else:
                    raise VideoTransformError(
                        f"Tệp video footage '{media_p.name}' bị lỗi hoặc không thể đọc được bằng ffprobe: {probe_err}"
                    ) from probe_err

        # 3. Transformer setup & timing decision
        t_config = transform_config or TransformationConfig(
            target_width=self._mux_config.video_width,
            target_height=self._mux_config.video_height,
            target_fps=self._mux_config.video_fps,
        )
        transformer = VideoTransformer(config=t_config, binary_manager=self._binary_manager)

        timing_decision = transformer.calculate_timing_fit(
            source_duration_sec=source_duration,
            target_duration_sec=duration,
            start_offset_sec=start_offset_sec,
            is_image=is_image,
        )

        # 4. Resolve destination path
        if output_path is not None:
            dest_p = Path(output_path).resolve()
        else:
            dest_dir = self._app_config.paths.cache_temp_scenes_dir / project_id
            dest_p = dest_dir / f"scene_{scene_idx:03d}.mp4"

        dest_p.parent.mkdir(parents=True, exist_ok=True)

        # 5. Build FFmpeg command
        ffmpeg_info = self._binary_manager.check_binary("ffmpeg")
        if not ffmpeg_info.is_available or not ffmpeg_info.path:
            raise FileNotFoundError("ffmpeg binary is required but not found in bin/ or PATH.")

        cmd = [str(ffmpeg_info.path), "-y"]

        # Input 0: Media
        if is_image:
            cmd.extend([
                "-loop", "1",
                "-framerate", str(self._mux_config.video_fps),
                "-t", f"{duration:.4f}",
                "-i", str(media_p),
            ])
        else:
            if timing_decision.action == "trim" and start_offset_sec > 0:
                cmd.extend(["-ss", f"{start_offset_sec:.3f}"])
            cmd.extend(["-i", str(media_p)])

        # Input 1: Voiceover audio
        cmd.extend(["-i", str(vo_p)])

        # Input 2: Ambient audio (optional)
        has_ambient = False
        if ambient_audio_path:
            amb_p = Path(ambient_audio_path).resolve()
            if amb_p.exists() and amb_p.stat().st_size > 0:
                has_ambient = True
                cmd.extend(["-i", str(amb_p)])

        # Compile video filter (with auto black-bar crop detection)
        pre_crop = None
        if not is_image and not source_is_vertical and getattr(t_config, "detect_black_bars", True):
            try:
                pre_crop = detect_crop_region(media_p, binary_manager=self._binary_manager)
            except Exception as e:
                logger.debug(f"detect_crop_region skipped: {e}")

        v_filter, v_out_label = transformer.compile_video_filter(
            timing_decision=timing_decision,
            source_is_vertical=source_is_vertical,
            is_image=is_image,
            pre_crop=pre_crop,
        )

        # Audio mixing filter
        audio_filters = []
        if has_ambient:
            audio_filters.append(
                f"[1:a]volume={self._mux_config.voiceover_volume:.2f},"
                f"aformat=sample_rates={self._mux_config.audio_sample_rate}:channel_layouts=stereo[vo_clean];"
                f"[2:a]aloop=loop=-1:size=2e+09,volume={self._mux_config.ambient_volume:.2f},"
                f"aformat=sample_rates={self._mux_config.audio_sample_rate}:channel_layouts=stereo[amb_clean];"
                f"[vo_clean][amb_clean]amix=inputs=2:duration=first:dropout_transition=2[a_mix]"
            )
            a_out_label = "a_mix"
        else:
            audio_filters.append(
                f"[1:a]volume={self._mux_config.voiceover_volume:.2f},"
                f"aformat=sample_rates={self._mux_config.audio_sample_rate}:channel_layouts=stereo[a_out]"
            )
            a_out_label = "a_out"

        full_filter_complex = f"{v_filter};{';'.join(audio_filters)}"

        cmd.extend([
            "-filter_complex", full_filter_complex,
            "-map", f"[{v_out_label}]",
            "-map", f"[{a_out_label}]",
            "-c:v", self._mux_config.video_codec,
            "-crf", "18",
            "-preset", self._mux_config.video_preset,
            "-profile:v", self._mux_config.video_profile,
            "-level:v", self._mux_config.video_level,
            "-pix_fmt", self._mux_config.video_pix_fmt,
            "-r", str(self._mux_config.video_fps),
            "-c:a", self._mux_config.audio_codec,
            "-b:a", self._mux_config.audio_bitrate,
            "-ar", str(self._mux_config.audio_sample_rate),
            "-t", f"{duration:.4f}",
            str(dest_p),
        ])

        # 6. Execute FFmpeg
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.SubprocessError as err:
            raise VideoTransformError(f"FFmpeg process execution failed: {err}") from err

        if proc.returncode != 0:
            raise VideoTransformError(
                f"FFmpeg failed (exit code {proc.returncode}):\n{proc.stderr}"
            )

        # 7. Probe rendered result to ensure compliance
        result_probe = probe_video(dest_p, binary_manager=self._binary_manager)

        return SceneMuxResult(
            scene_id=scene_idx,
            project_id=project_id,
            output_path=dest_p,
            duration_sec=result_probe.duration_sec,
            width=result_probe.width,
            height=result_probe.height,
            fps=result_probe.fps,
            has_audio=result_probe.has_audio,
            timing_action=timing_decision.action,
        )
