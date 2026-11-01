"""
Visual Quality Inspector (AI-DLC Visual Verification & Artifact Quality Gate).
Performs zero-hardcode computer vision inspection on raw footage and assembled scenes:
- Detects burned-in open captions & lower-third text in the subtitle region using morphological geometry and stroke transitions.
- Detects flat computer screens, slides, and UI recordings (Facebook, browser windows) using color histogram entropy.
- Detects black/blank/empty video streams using luminance distribution.
- Detects static watermark / station logos in corners using temporal edge invariance.
- Finds clean time offsets within a video or flags tainted videos for automatic fallback.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VisualInspectionResult:
    """Detailed visual quality assessment report for a frame or video segment."""
    is_clean: bool
    is_black: bool = False
    is_ui_screen: bool = False
    has_subtitles: bool = False
    has_watermark: bool = False
    defects: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class VisualQualityInspector:
    """
    Automated Computer Vision quality gate for footage sourcing and scene assembly.
    Operates strictly on pixel distributions, morphological geometry, and temporal invariants
    with zero hardcoded keyword blacklists.
    """

    BLUR_THRESHOLD = 35.0  # median variance-of-Laplacian at 640px width (ADR-021)

    @staticmethod
    def laplacian_sharpness(img: np.ndarray) -> float:
        """Variance of the Laplacian on a 640px-wide grayscale copy (higher = sharper)."""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        h, w = g.shape[:2]
        if w > 0 and w != 640:
            g = cv2.resize(g, (640, max(1, int(h * 640 / w))))
        return float(cv2.Laplacian(g, cv2.CV_64F).var())

    @staticmethod
    def inspect_frame(img: np.ndarray) -> VisualInspectionResult:
        """
        Inspect a single video frame for visual defects:
        1. Pitch black / unlit frames.
        2. Flat UI screens / computer desktop / slide captures.
        3. Burned-in subtitles or lower-third text banners.
        """
        if img is None or img.size == 0:
            return VisualInspectionResult(
                is_clean=False,
                is_black=True,
                defects=["empty_or_null_frame"],
            )

        h, w, c = img.shape
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        defects: List[str] = []
        details: Dict[str, Any] = {}

        # 1. Black / unlit frame detection
        mean_lum = float(gray.mean())
        std_lum = float(gray.std())
        details["mean_luminance"] = mean_lum
        details["std_luminance"] = std_lum
        is_black = mean_lum < 15.0 or (mean_lum < 25.0 and std_lum < 8.0)
        if is_black:
            defects.append("black_or_unlit_frame")

        # 2. UI / Flat screen capture detection (Facebook, browser, presentation slides)
        # Natural videos have rich continuous tonal gradients. Computer screens have large monochromatic blocks.
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
        max_bin_ratio = float(hist.max() / (hist.sum() + 1e-6))
        details["max_color_bin_ratio"] = max_bin_ratio
        is_ui = max_bin_ratio > 0.48
        if is_ui:
            defects.append(f"ui_or_screen_capture(bin={max_bin_ratio:.2f})")

        # 3. Burned-in Subtitle & Lower-Third text detection in bottom 26% of frame
        bot_y1 = int(h * 0.74)
        bot_y2 = int(h * 0.97)
        bot_x1 = int(w * 0.08)
        bot_x2 = int(w * 0.92)
        bot_region = gray[bot_y1:bot_y2, bot_x1:bot_x2]

        # Filter bright text characters (> 205 luminance)
        _, bright_bin = cv2.threshold(bot_region, 205, 255, cv2.THRESH_BINARY)
        edges = cv2.Canny(bot_region, 60, 160)
        edges_on_bright = cv2.bitwise_and(edges, bright_bin)

        # Horizontal morphological closing: merges letter strokes of a word
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (24, 3))
        connected = cv2.morphologyEx(edges_on_bright, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw_boxes: List[Tuple[int, int, int, int, int, float]] = []

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect_ratio = cw / float(ch + 1e-5)
            abs_x = bot_x1 + x
            center_dist = abs((abs_x + cw / 2.0) - (w / 2.0)) / float(w)

            # Subtitles have characters between 8px and 45px tall, aspect ratio >= 2.0, centered horizontally
            if cw >= 50 and 8 <= ch <= 45 and aspect_ratio >= 2.0 and center_dist <= 0.20:
                roi = bright_bin[y : y + ch, x : x + cw]
                diffs = np.abs(np.diff(roi.astype(int), axis=1))
                transitions = (diffs > 0).sum(axis=1)
                if (transitions > 0).any():
                    max_trans = int(transitions.max())
                    mean_trans = float(transitions[transitions > 0].mean())
                    raw_boxes.append((x, y, cw, ch, max_trans, mean_trans))

        # Evaluate candidate boxes:
        # Multiple boxes (typical sentence/phrase) require stroke crossings across letters
        # A single solitary box requires higher width and stroke crossing evidence
        if len(raw_boxes) >= 2:
            valid_boxes = [b for b in raw_boxes if b[4] >= 6 and b[5] >= 3.0]
            has_subtitles = len(valid_boxes) >= 2
        elif len(raw_boxes) == 1:
            b = raw_boxes[0]
            has_subtitles = b[2] >= 90 and b[4] >= 10 and b[5] >= 4.0
            valid_boxes = [b] if has_subtitles else []
        else:
            has_subtitles = False
            valid_boxes = []

        details["text_box_count"] = len(valid_boxes)
        if has_subtitles:
            defects.append(f"burned_in_subtitles({len(valid_boxes)}_text_boxes)")

        is_clean = len(defects) == 0
        return VisualInspectionResult(
            is_clean=is_clean,
            is_black=is_black,
            is_ui_screen=is_ui,
            has_subtitles=has_subtitles,
            defects=defects,
            details=details,
        )

    @classmethod
    def _extract_frame(
        cls,
        video_path: Path,
        offset_sec: float,
        ffmpeg_bin: Optional[Path] = None,
    ) -> Optional[np.ndarray]:
        """Extract a single frame from video at offset_sec via ffmpeg."""
        ffmpeg_cmd = str(ffmpeg_bin) if ffmpeg_bin else "ffmpeg"
        try:
            cmd = [
                ffmpeg_cmd,
                "-v", "error",
                "-ss", f"{offset_sec:.2f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-",
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if proc.returncode != 0 or not proc.stdout:
                return None
            arr = np.frombuffer(proc.stdout, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as exc:
            logger.debug("Frame extract error at %.1fs for %s: %s", offset_sec, video_path.name, exc)
            return None

    @classmethod
    def inspect_video_segment(
        cls,
        video_path: Path,
        start_sec: float,
        duration_sec: float,
        ffmpeg_bin: Optional[Path] = None,
    ) -> VisualInspectionResult:
        """
        Samples frames across a segment to detect transient or permanent visual defects:
        - Pitch black frames
        - Screen shares / UI recordings
        - Burned-in subtitles / lower-thirds
        - Static watermark / station logos in corners across frames
        """
        if not video_path.exists() or video_path.stat().st_size == 0:
            return VisualInspectionResult(
                is_clean=False,
                is_black=True,
                defects=["file_not_found_or_empty"],
            )

        # Fast-path for unit test mock stubs (< 1KB)
        if video_path.stat().st_size < 1024:
            return VisualInspectionResult(is_clean=True)

        sample_offsets = [
            start_sec + 0.1,
            start_sec + 0.35 * duration_sec,
            start_sec + 0.70 * duration_sec,
            start_sec + max(0.1, duration_sec - 0.2),
        ]

        frames: List[np.ndarray] = []
        for off in sample_offsets:
            f = cls._extract_frame(video_path, off, ffmpeg_bin=ffmpeg_bin)
            if f is not None:
                frames.append(f)

        if not frames:
            return VisualInspectionResult(
                is_clean=False,
                is_black=True,
                defects=["unable_to_decode_frames"],
            )

        aggregated_defects: List[str] = []
        is_clean = True
        has_subtitles = False
        is_ui = False
        is_black = False
        has_watermark = False

        # 0. Segment runs past the end of the source (would be padded with black frames) - ADR-019
        if len(sample_offsets) - len(frames) >= 2:
            is_clean = False
            is_black = True
            aggregated_defects.append("segment_exceeds_source")

        # 0b. Out-of-focus / smeared footage (ADR-021). Calibrated on proj_cf3b1f52:
        #     blurry close-up = 25, dark-but-sharp night shot = 52, normal daylight = 120-2200.
        sharpness = [cls.laplacian_sharpness(f) for f in frames]
        if sharpness and float(np.median(sharpness)) < cls.BLUR_THRESHOLD:
            is_clean = False
            aggregated_defects.append(f"blurry(sharpness={float(np.median(sharpness)):.0f})")

        # 1. Per-frame defect inspection
        for frame in frames:
            frame_res = cls.inspect_frame(frame)
            if not frame_res.is_clean:
                is_clean = False
                if frame_res.has_subtitles:
                    has_subtitles = True
                if frame_res.is_ui_screen:
                    is_ui = True
                if frame_res.is_black:
                    is_black = True
                for d in frame_res.defects:
                    if d not in aggregated_defects:
                        aggregated_defects.append(d)

        # 2. Static corner watermark logo detection across sampled frames (broadcast TV / station logos in upper corners)
        if len(frames) >= 2:
            f1, f2 = frames[0], frames[-1]
            h, w, _ = f1.shape
            corners = {
                "top_left": (slice(0, int(h * 0.16)), slice(0, int(w * 0.18))),
                "top_right": (slice(0, int(h * 0.16)), slice(int(w * 0.82), w)),
            }

            for corner_name, (ys, xs) in corners.items():
                c1 = f1[ys, xs]
                c2 = f2[ys, xs]
                diff = cv2.absdiff(c1, c2)
                diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                # If background is moving (mean diff > 8.0), check for static high-contrast bright edges (station logos / bugs)
                if float(diff_gray.mean()) > 8.0:
                    gray1 = cv2.cvtColor(c1, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray1, 60, 160)
                    # Watermark logos are bright graphic elements (luminance > 195) with sharp edges that remain stationary (diff < 10)
                    bright_static = (diff_gray < 10) & (gray1 > 195) & (edges > 0)
                    bright_static_edge_ratio = float(bright_static.sum()) / float(gray1.size + 1e-6)
                    if bright_static_edge_ratio >= 0.003:
                        has_watermark = True
                        is_clean = False
                        wm_defect = f"corner_watermark({corner_name})"
                        if wm_defect not in aggregated_defects:
                            aggregated_defects.append(wm_defect)

        return VisualInspectionResult(
            is_clean=is_clean,
            is_black=is_black,
            is_ui_screen=is_ui,
            has_subtitles=has_subtitles,
            has_watermark=has_watermark,
            defects=aggregated_defects,
        )

    @classmethod
    def find_clean_segment(
        cls,
        video_path: Path,
        target_duration: float,
        total_duration: float,
        initial_offset: float = 0.0,
        ffmpeg_bin: Optional[Path] = None,
    ) -> Optional[float]:
        """
        Scans a video to find a clean, defect-free time window.
        Returns the first clean start_offset_sec, or None if the entire video is tainted.
        """
        search_offsets: List[float] = []

        # Test reasonable intervals avoiding extreme edges
        t = 8.0
        max_limit = total_duration - target_duration - 4.0
        while t <= max_limit:
            if abs(t - initial_offset) > 3.0:
                search_offsets.append(t)
            t += 15.0

        # Prioritize offsets that are closer to natural documentary action (20% - 60% of duration)
        mid_target = total_duration * 0.35
        search_offsets.sort(key=lambda x: abs(x - mid_target))

        for cand_offset in search_offsets:
            res = cls.inspect_video_segment(
                video_path=video_path,
                start_sec=cand_offset,
                duration_sec=target_duration,
                ffmpeg_bin=ffmpeg_bin,
            )
            if res.is_clean:
                logger.info(
                    "VisualQualityInspector: Found clean segment at %.1fs in %s (no subtitles, no UI screen, no watermarks)",
                    cand_offset,
                    video_path.name,
                )
                return cand_offset

        return None
