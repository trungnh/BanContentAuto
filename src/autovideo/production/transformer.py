"""
Visual Filter & Aspect Ratio Transformation Engine (WU-05, REQ-B2-04, VAC-UI-03).
Transforms vertical (9:16) and arbitrary aspect ratio media to standardized 16:9 Full HD (1920x1080)
with blurred margin backgrounds, cinematic slow-motion duration fitting, Ken Burns zoom, and visual accents.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autovideo.core.binary_manager import BinaryManager


class VideoProbeError(Exception):
    """Raised when ffprobe fails to parse media metadata."""
    pass


class VideoTransformError(Exception):
    """Raised when an FFmpeg transformation process encounters a failure."""
    pass


@dataclass(frozen=True)
class VideoProbeInfo:
    """Comprehensive media container and stream metadata."""

    file_path: Path
    width: int
    height: int
    aspect_ratio: float
    is_vertical: bool
    duration_sec: float
    fps: float
    has_audio: bool
    codec_name: str
    total_frames: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "is_vertical": self.is_vertical,
            "duration_sec": self.duration_sec,
            "fps": self.fps,
            "has_audio": self.has_audio,
            "codec_name": self.codec_name,
            "total_frames": self.total_frames,
        }


def probe_video(
    video_path: Path | str,
    binary_manager: Optional[BinaryManager] = None,
) -> VideoProbeInfo:
    """
    Probe a video or image file using ffprobe and extract geometry and timing.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If file is empty (0 bytes).
        VideoProbeError: If ffprobe cannot parse video streams.
    """
    path = Path(video_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Video file is empty (0 bytes): {path}")

    bm = binary_manager or BinaryManager()
    ffprobe_info = bm.check_binary("ffprobe")
    if not ffprobe_info.is_available or not ffprobe_info.path:
        raise FileNotFoundError("ffprobe binary is required but not found in bin/ or PATH.")

    cmd = [
        str(ffprobe_info.path),
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.SubprocessError as err:
        raise VideoProbeError(f"Failed to invoke ffprobe on '{path}': {err}") from err

    if proc.returncode != 0:
        raise VideoProbeError(f"ffprobe exited with code {proc.returncode}: {proc.stderr}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as err:
        raise VideoProbeError(f"ffprobe output invalid JSON: {err}") from err

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream: Optional[Dict[str, Any]] = None
    has_audio = False

    for stream in streams:
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio":
            has_audio = True

    if not video_stream:
        raise VideoProbeError(f"No video stream detected in '{path}'.")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    if width <= 0 or height <= 0:
        raise VideoProbeError(f"Invalid video dimensions: {width}x{height}")

    pix_fmt = video_stream.get("pix_fmt")
    if pix_fmt in ("unknown", "none"):
        raise VideoProbeError(
            f"Video '{path.name}' has invalid or unspecified pixel format '{pix_fmt}' (corrupted or truncated file)."
        )

    aspect_ratio = round(width / height, 4)
    is_vertical = aspect_ratio < 1.0

    # Parse duration: prioritize format.duration, then stream.duration
    duration_str = format_info.get("duration") or video_stream.get("duration")
    duration_sec = float(duration_str) if duration_str else 0.0

    # Parse fps from r_frame_rate e.g. "30/1" or "30000/1001"
    fps_raw = video_stream.get("r_frame_rate", "30/1")
    fps = 30.0
    if "/" in str(fps_raw):
        num, den = str(fps_raw).split("/", 1)
        try:
            den_float = float(den)
            fps = float(num) / den_float if den_float != 0 else 30.0
        except ValueError:
            fps = 30.0
    else:
        try:
            fps = float(fps_raw)
        except ValueError:
            fps = 30.0

    fps = round(fps, 2)

    nb_frames = video_stream.get("nb_frames")
    total_frames = int(nb_frames) if nb_frames and str(nb_frames).isdigit() else None
    if total_frames is None and duration_sec > 0:
        total_frames = int(round(duration_sec * fps))

    codec_name = video_stream.get("codec_name", "unknown")

    return VideoProbeInfo(
        file_path=path,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        is_vertical=is_vertical,
        duration_sec=duration_sec,
        fps=fps,
        has_audio=has_audio,
        codec_name=codec_name,
        total_frames=total_frames,
    )


def detect_crop_region(
    video_path: Path | str,
    binary_manager: Optional[BinaryManager] = None,
    sample_frames: int = 25,
) -> Optional[str]:
    """
    Run ffmpeg with cropdetect to determine if the video has hardcoded black bars.
    Returns FFmpeg crop filter string (e.g. 'crop=1408:1072:258:4') if significant
    black bars are detected, or None if the video is full frame.
    """
    path = Path(video_path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        return None

    bm = binary_manager or BinaryManager()
    ffmpeg_info = bm.check_binary("ffmpeg")
    if not ffmpeg_info.is_available or not ffmpeg_info.path:
        return None

    cmd = [
        str(ffmpeg_info.path),
        "-i", str(path),
        "-vf", "cropdetect=24:16:0",
        "-vframes", str(sample_frames),
        "-f", "null",
        "-",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        crops = re.findall(r"crop=(\d+:\d+:\d+:\d+)", proc.stderr)
        if not crops:
            return None

        # Take the most frequent crop from the latter half of sampled frames
        recent_crops = crops[len(crops) // 2 :] if len(crops) > 2 else crops
        most_common = Counter(recent_crops).most_common(1)[0][0]
        w_c, h_c, x_c, y_c = [int(v) for v in most_common.split(":")]

        # Get original video stream dimensions to check for significance
        probe_info = probe_video(path, binary_manager=bm)
        in_w, in_h = probe_info.width, probe_info.height

        # A crop is considered significant if width or height loses >= 32px or margins >= 16px
        if (in_w - w_c >= 32) or (in_h - h_c >= 32) or x_c >= 16 or y_c >= 16:
            return f"crop={w_c}:{h_c}:{x_c}:{y_c}"

        return None
    except Exception:
        return None


@dataclass
class HighlightConfig:
    """Configuration for visual warning indicator or accent highlight."""

    enabled: bool = True
    type: str = "box"  # "box" or "circle"
    color: str = "red"
    opacity: float = 0.80
    x: Optional[int] = None
    y: Optional[int] = None
    width: int = 240
    height: int = 240
    thickness: int = 5


@dataclass
class TransformationConfig:
    """Parameters defining 16:9 visual padding and filter behavior."""

    target_width: int = 1920
    target_height: int = 1080
    target_fps: int = 30
    enable_blurred_margin: bool = True
    blur_radius: int = 25
    blur_power: int = 5
    background_darkness: float = 0.40  # 40% darkening
    enable_ken_burns: bool = False
    ken_burns_zoom_speed: float = 0.0015
    ken_burns_max_zoom: float = 1.15
    highlight: Optional[HighlightConfig] = None
    safe_margin_zoom: float = 1.0  # Optional zoom crop (e.g. 1.06 - 1.08) to eliminate corner broadcast logos / TV bugs
    detect_black_bars: bool = True  # Automatically detect and crop hardcoded black bars (windowbox/letterbox)


@dataclass(frozen=True)
class TimingFitDecision:
    """Calculated duration fitting strategy for a scene."""

    action: str  # "trim" | "slow_motion" | "loop" | "image_still"
    source_duration_sec: float
    target_duration_sec: float
    slowmo_factor: float
    trim_start_sec: float
    effective_duration_sec: float


class VideoTransformer:
    """
    Video Transformation Engine (B2).
    Generates deterministic FFmpeg filter graphs to transform clips into
    uniform 16:9 Full HD atomic scenes.
    """

    def __init__(
        self,
        config: Optional[TransformationConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self.config = config or TransformationConfig()
        self.bm = binary_manager or BinaryManager()

    def calculate_timing_fit(
        self,
        source_duration_sec: float,
        target_duration_sec: float,
        start_offset_sec: float = 0.0,
        max_slowmo_deficit: float = 0.20,
        is_image: bool = False,
    ) -> TimingFitDecision:
        """
        Determine whether to trim, slow-down, loop, or still-frame a clip
        to fit the exact voiceover audio duration (T_audio).

        Rules:
        - If clip is an image: action="image_still", exact frame duration.
        - If clip_duration >= target_duration: action="trim", cut exactly T_audio.
        - If clip is shorter than T_audio <= 20% deficit (i.e. source >= target * 0.80):
          apply cinematic slow-motion via PTS factor (factor = target / source <= 1.25).
        - If clip is shorter than T_audio > 20% deficit: action="loop".
        """
        if is_image or source_duration_sec <= 0.0:
            return TimingFitDecision(
                action="image_still",
                source_duration_sec=0.0,
                target_duration_sec=target_duration_sec,
                slowmo_factor=1.0,
                trim_start_sec=0.0,
                effective_duration_sec=target_duration_sec,
            )

        if source_duration_sec >= target_duration_sec:
            return TimingFitDecision(
                action="trim",
                source_duration_sec=source_duration_sec,
                target_duration_sec=target_duration_sec,
                slowmo_factor=1.0,
                trim_start_sec=start_offset_sec,
                effective_duration_sec=target_duration_sec,
            )

        deficit_ratio = (target_duration_sec - source_duration_sec) / target_duration_sec
        if deficit_ratio <= max_slowmo_deficit:
            # Slower speed: factor > 1.0 (e.g. 5.0 / 4.2 = 1.190476)
            factor = target_duration_sec / source_duration_sec
            return TimingFitDecision(
                action="slow_motion",
                source_duration_sec=source_duration_sec,
                target_duration_sec=target_duration_sec,
                slowmo_factor=factor,
                trim_start_sec=start_offset_sec,
                effective_duration_sec=target_duration_sec,
            )

        return TimingFitDecision(
            action="loop",
            source_duration_sec=source_duration_sec,
            target_duration_sec=target_duration_sec,
            slowmo_factor=1.0,
            trim_start_sec=start_offset_sec,
            effective_duration_sec=target_duration_sec,
        )

    def build_blurred_margin_filter(
        self,
        input_label: str = "0:v",
        output_label: str = "v_pad",
    ) -> str:
        """
        Builds the 16:9 blurred background margin filter_complex string:
        - Layer 1 (Background): Scaled to fill 1920x1080 (cropped), boxblur, darkened by 40%.
        - Layer 2 (Foreground): Scaled to fit 100% aspect ratio, centered.
        - Composite: Foreground overlaid on Background.
        """
        w = self.config.target_width
        h = self.config.target_height
        radius = self.config.blur_radius
        power = self.config.blur_power
        # Darkness: eq=brightness=-0.15 represents ~40% luminance decrease
        darkness_val = -round(self.config.background_darkness * 0.375, 3)

        filter_chain = (
            f"[{input_label}]split=2[bg_in][fg_in];"
            f"[bg_in]scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,"
            f"crop={w}:{h},boxblur={radius}:{power},eq=brightness={darkness_val}[bg_blurred];"
            f"[fg_in]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fg_scaled];"
            f"[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2[{output_label}]"
        )
        return filter_chain

    def build_ken_burns_filter(
        self,
        input_label: str = "0:v",
        output_label: str = "v_kb",
        total_frames: int = 150,
    ) -> str:
        """Builds a subtle Ken Burns zoom-in filter using zoompan."""
        w = self.config.target_width
        h = self.config.target_height
        fps = self.config.target_fps
        speed = self.config.ken_burns_zoom_speed
        max_z = self.config.ken_burns_max_zoom

        return (
            f"[{input_label}]zoompan=z='min(zoom+{speed},{max_z})':"
            f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={w}x{h}:fps={fps}[{output_label}]"
        )

    def build_highlight_filter(
        self,
        input_label: str,
        output_label: str,
        highlight: HighlightConfig,
    ) -> str:
        """Builds a visual warning indicator (bounding box/frame) using drawbox."""
        w = highlight.width
        h = highlight.height
        x = highlight.x if highlight.x is not None else f"(iw-{w})/2"
        y = highlight.y if highlight.y is not None else f"(ih-{h})/2"
        color = highlight.color
        opacity = highlight.opacity
        thickness = highlight.thickness

        return (
            f"[{input_label}]drawbox=x={x}:y={y}:w={w}:h={h}:"
            f"color={color}@{opacity}:t={thickness}[{output_label}]"
        )

    def compile_video_filter(
        self,
        timing_decision: TimingFitDecision,
        source_is_vertical: bool = True,
        is_image: bool = False,
        pre_crop: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Compile complete filter_complex pipeline for video stream.
        Returns: (filter_complex_str, final_output_label)
        """
        stages: List[str] = []
        current_label = "0:v"

        # 1. Timing manipulation: slow-motion or loop
        if timing_decision.action == "slow_motion" and timing_decision.slowmo_factor > 1.0:
            factor = timing_decision.slowmo_factor
            next_label = "v_slow"
            stages.append(
                f"[{current_label}]setpts={factor:.6f}*PTS,fps={self.config.target_fps}[{next_label}]"
            )
            current_label = next_label
        elif timing_decision.action == "loop":
            next_label = "v_loop"
            # Loop video frames continuously to cover target duration
            stages.append(
                f"[{current_label}]loop=loop=-1:size=32767:start=0,setpts=N/({self.config.target_fps}*TB)[{next_label}]"
            )
            current_label = next_label

        # 2. Aspect Ratio Transformation (100% Zero Black Bars: Fill & Center Crop)
        if self.config.enable_blurred_margin and (source_is_vertical or is_image):
            next_label = "v_pad"
            stages.append(self.build_blurred_margin_filter(current_label, next_label))
            current_label = next_label
        else:
            # Fill 16:9 canvas cleanly via scale-increase + center-crop (Zero Letterbox / Zero Pillarbox)
            w = self.config.target_width
            h = self.config.target_height
            zoom = max(1.0, float(getattr(self.config, "safe_margin_zoom", 1.0) or 1.0))
            if zoom > 1.0:
                scale_w = int(round(w * zoom))
                scale_h = int(round(h * zoom))
                if scale_w % 2 != 0:
                    scale_w += 1
                if scale_h % 2 != 0:
                    scale_h += 1
            else:
                scale_w, scale_h = w, h

            next_label = "v_scaled"
            crop_prefix = f"{pre_crop}," if pre_crop else ""
            stages.append(
                f"[{current_label}]{crop_prefix}scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h}:(in_w-out_w)/2:(in_h-out_h)/2,fps={self.config.target_fps}[{next_label}]"
            )
            current_label = next_label

        # 3. Ken Burns Zoom (Optional)
        if self.config.enable_ken_burns:
            total_frames = int(round(timing_decision.effective_duration_sec * self.config.target_fps))
            next_label = "v_kb"
            stages.append(self.build_ken_burns_filter(current_label, next_label, total_frames=max(30, total_frames)))
            current_label = next_label

        # 4. Highlight Indicator (Optional)
        if self.config.highlight and self.config.highlight.enabled:
            next_label = "v_highlight"
            stages.append(self.build_highlight_filter(current_label, next_label, self.config.highlight))
            current_label = next_label

        filter_complex = ";".join(stages)
        return filter_complex, current_label
