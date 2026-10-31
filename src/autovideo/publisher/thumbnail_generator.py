"""
Counterpoint Thumbnail Generator (B4, REQ-B4-01, VAC-UI-04).
Generates high-contrast 16:9 thumbnails adhering to:
1. The Counterpoint Law (Luật Đối Nghịch): Thumbnail text must NEVER repeat words
   from the screenplay/video title (rational title vs emotional/tension thumbnail).
2. YouTube Safe Zone Enforcement: Strictly keeps the bottom-right 20% area
   (X: 80%-100%, Y: 75%-100%) completely clear of text, badges, or critical visuals
   so the YouTube duration badge never covers essential content.
3. High-Contrast Dramatic Themes: Dark Dramatic, Red Alert Warning, Electric Cyan,
   Gold Luxury, and Neon Toxic.
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


# Standard stop words in Vietnamese & English to filter out before counterpoint comparison
STOP_WORDS = {
    "của", "và", "là", "trong", "một", "các", "những", "được", "có", "cho",
    "với", "đã", "đang", "sẽ", "về", "tại", "này", "đó", "ra", "lại", "để",
    "như", "theo", "khi", "từ", "lên", "vào", "ở", "nhiều", "bị", "bởi",
    "không", "thì", "mà", "nhưng", "rất", "hay", "hoặc", "nếu", "nên",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with",
    "of", "by", "from", "up", "about", "into", "over", "after", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does"
}


class CounterpointViolationError(ValueError):
    """Raised when thumbnail text repeats words from the video title."""
    pass


class SafeZoneViolationError(ValueError):
    """Raised when text or graphics intrude into YouTube's duration badge safe zone."""
    pass


@dataclass
class SafeZoneRect:
    """Bounding box for YouTube timestamp badge safe zone."""
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def contains_point(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def intersects(self, bbox: Tuple[int, int, int, int]) -> bool:
        """Returns True if given bbox (bx1, by1, bx2, by2) intersects this safe zone."""
        bx1, by1, bx2, by2 = bbox
        return not (bx2 < self.x1 or bx1 > self.x2 or by2 < self.y1 or by1 > self.y2)


@dataclass
class ThemePalette:
    """Color palette and visual styling tokens for thumbnail generation."""
    name: str
    bg_start: Tuple[int, int, int]
    bg_end: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    text_color: Tuple[int, int, int]
    stroke_color: Tuple[int, int, int]
    badge_bg: Tuple[int, int, int]
    badge_text: Tuple[int, int, int]
    highlight_accent: Tuple[int, int, int]


THEMES: Dict[str, ThemePalette] = {
    "dark_dramatic": ThemePalette(
        name="dark_dramatic",
        bg_start=(11, 15, 23),
        bg_end=(28, 37, 54),
        accent=(220, 38, 38),  # Crimson Alert
        text_color=(255, 255, 255),
        stroke_color=(0, 0, 0),
        badge_bg=(220, 38, 38),
        badge_text=(255, 255, 255),
        highlight_accent=(250, 204, 21),  # Gold warning
    ),
    "red_alert": ThemePalette(
        name="red_alert",
        bg_start=(24, 6, 6),
        bg_end=(45, 10, 10),
        accent=(239, 68, 68),
        text_color=(255, 255, 255),
        stroke_color=(15, 2, 2),
        badge_bg=(239, 68, 68),
        badge_text=(255, 255, 255),
        highlight_accent=(254, 240, 138),
    ),
    "electric_cyan": ThemePalette(
        name="electric_cyan",
        bg_start=(10, 18, 30),
        bg_end=(19, 30, 49),
        accent=(0, 229, 255),  # Electric Cyan
        text_color=(255, 255, 255),
        stroke_color=(5, 10, 20),
        badge_bg=(0, 229, 255),
        badge_text=(11, 15, 23),
        highlight_accent=(0, 229, 255),
    ),
    "gold_luxury": ThemePalette(
        name="gold_luxury",
        bg_start=(15, 12, 8),
        bg_end=(35, 28, 18),
        accent=(234, 179, 8),  # Warm Metallic Gold
        text_color=(255, 255, 255),
        stroke_color=(10, 8, 5),
        badge_bg=(234, 179, 8),
        badge_text=(15, 12, 8),
        highlight_accent=(253, 224, 71),
    ),
    "neon_toxic": ThemePalette(
        name="neon_toxic",
        bg_start=(10, 16, 12),
        bg_end=(18, 32, 24),
        accent=(34, 197, 94),  # Toxic Green
        text_color=(255, 255, 255),
        stroke_color=(2, 10, 5),
        badge_bg=(34, 197, 94),
        badge_text=(10, 16, 12),
        highlight_accent=(236, 72, 153),  # Hot Magenta
    ),
}


def normalize_words(text: str) -> List[str]:
    """Tokenize and normalize text into clean words for comparison."""
    # Remove symbols and punctuation
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 3]
    return [w for w in words if w not in STOP_WORDS]


def validate_counterpoint(title: str, thumbnail_text: str) -> Tuple[bool, List[str]]:
    """
    Validates whether the thumbnail text adheres to the Counterpoint Law:
    Never repeating keywords from the video title.

    Returns:
        (is_valid, common_words)
    """
    title_words = set(normalize_words(title))
    thumb_words = set(normalize_words(thumbnail_text))

    overlap = sorted(list(title_words.intersection(thumb_words)))
    is_valid = len(overlap) == 0
    return is_valid, overlap


class ThumbnailGenerator:
    """
    Automated High-Impact Thumbnail Generator adhering to YouTube Safe Zone rules
    and the Counterpoint Law (REQ-B4-01).
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        safe_zone_width_ratio: float = 0.20,
        safe_zone_height_ratio: float = 0.25,
        default_theme: str = "dark_dramatic",
    ) -> None:
        self.width = width
        self.height = height
        self.safe_zone_width_ratio = safe_zone_width_ratio
        self.safe_zone_height_ratio = safe_zone_height_ratio
        self.default_theme = default_theme

    def get_safe_zone(self) -> SafeZoneRect:
        """
        Calculates YouTube badge forbidden zone in bottom-right corner.
        Area: X in [width * (1 - ratio), width], Y in [height * (1 - ratio), height].
        """
        x1 = int(self.width * (1.0 - self.safe_zone_width_ratio))
        y1 = int(self.height * (1.0 - self.safe_zone_height_ratio))
        return SafeZoneRect(x1=x1, y1=y1, x2=self.width, y2=self.height)

    def is_box_safe(self, bbox: Tuple[int, int, int, int]) -> bool:
        """Checks if a bounding box (x1, y1, x2, y2) stays out of the forbidden safe zone."""
        safe_zone = self.get_safe_zone()
        return not safe_zone.intersects(bbox)

    def _get_best_font(self, size: int) -> ImageFont.ImageFont:
        """Finds and loads the best available TrueType font, or falls back to default."""
        font_candidates = [
            "arialbd.ttf",       # Arial Bold (Windows)
            "segoeuib.ttf",      # Segoe UI Bold (Windows)
            "tahoma.ttf",        # Tahoma
            "DejaVuSans-Bold.ttf",
            "Arial Bold.ttf",
            "Arial.ttf",
        ]
        for candidate in font_candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
        # Fallback to PIL default font
        return ImageFont.load_default()

    def _create_gradient_background(self, theme: ThemePalette) -> Image.Image:
        """Generates a high-contrast dual-tone gradient background with dark vignetting."""
        img = Image.new("RGB", (self.width, self.height), theme.bg_start)
        draw = ImageDraw.Draw(img)

        # Draw smooth vertical/diagonal gradient
        for y in range(self.height):
            ratio = y / self.height
            r = int(theme.bg_start[0] * (1.0 - ratio) + theme.bg_end[0] * ratio)
            g = int(theme.bg_start[1] * (1.0 - ratio) + theme.bg_end[1] * ratio)
            b = int(theme.bg_start[2] * (1.0 - ratio) + theme.bg_end[2] * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        # Add visual tension diagonal split line in background
        split_color = (
            int(theme.accent[0] * 0.35),
            int(theme.accent[1] * 0.35),
            int(theme.accent[2] * 0.35),
        )
        draw.line(
            [(0, self.height), (int(self.width * 0.7), 0)],
            fill=split_color,
            width=6,
        )

        # Apply subtle vignette / darkening around borders (especially bottom-right)
        vignette = Image.new("L", (self.width, self.height), 0)
        vignette_draw = ImageDraw.Draw(vignette)
        safe_zone = self.get_safe_zone()
        vignette_draw.rectangle(
            [safe_zone.x1 - 50, safe_zone.y1 - 50, self.width, self.height],
            fill=80,
        )
        vignette = vignette.filter(ImageFilter.GaussianBlur(radius=60))
        img = ImageChops.subtract(img, vignette.convert("RGB"))

        return img

    def _prepare_base_image(
        self,
        base_image: Union[Image.Image, Path, str],
        theme: ThemePalette,
    ) -> Image.Image:
        """Prepares and crops/enhances user-supplied base image."""
        if isinstance(base_image, (str, Path)):
            img = Image.open(base_image).convert("RGB")
        else:
            img = base_image.convert("RGB")

        # Resize and center-crop to 16:9 target dimensions
        target_ratio = self.width / self.height
        curr_ratio = img.width / img.height

        if curr_ratio > target_ratio:
            # Source is wider: crop horizontal
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Source is taller: crop vertical
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

        # Enhance contrast and add dramatic dark tint overlay
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.25)

        overlay = Image.new("RGBA", (self.width, self.height), (theme.bg_start[0], theme.bg_start[1], theme.bg_start[2], 110))
        img.paste(overlay, (0, 0), overlay)
        return img

    def generate(
        self,
        hook_text: str,
        tension_badge: Optional[str] = None,
        base_image: Optional[Union[Image.Image, Path, str]] = None,
        output_path: Optional[Union[Path, str]] = None,
        theme_name: Optional[str] = None,
        title_to_check: Optional[str] = None,
        strict_counterpoint: bool = True,
    ) -> Path:
        """
        Generates a 16:9 thumbnail with visual tension and safe zone compliance.

        Args:
            hook_text: Impactful thumbnail copy (never repeating video title words).
            tension_badge: Optional alert sticker (e.g., 'CẢNH BÁO', 'SỰ THẬT ĐỘC QUYỀN').
            base_image: Optional background image or scene frame.
            output_path: Destination path for rendered thumbnail.
            theme_name: Theme name from THEMES dictionary.
            title_to_check: Video title to validate against Counterpoint Law.
            strict_counterpoint: Whether to raise CounterpointViolationError if words overlap.

        Returns:
            Path of rendered thumbnail file.
        """
        # 1. Counterpoint Law Validation
        if title_to_check:
            is_valid, common = validate_counterpoint(title_to_check, hook_text)
            if not is_valid:
                msg = f"Counterpoint violation! Thumbnail text shares keywords with title: {common}"
                logger.warning(msg)
                if strict_counterpoint:
                    raise CounterpointViolationError(msg)

        theme = THEMES.get(theme_name or self.default_theme, THEMES["dark_dramatic"])

        # 2. Base Image or Gradient Canvas
        if base_image:
            canvas = self._prepare_base_image(base_image, theme)
        else:
            canvas = self._create_gradient_background(theme)

        draw = ImageDraw.Draw(canvas)
        safe_zone = self.get_safe_zone()

        # 3. Draw Tension Badge (Top-Left Safe Quadrant)
        if tension_badge:
            badge_font = self._get_best_font(size=44)
            badge_text = tension_badge.upper()
            bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            pad_x = 28
            pad_y = 14
            bx1 = 90
            by1 = 90
            bx2 = bx1 + text_w + (pad_x * 2)
            by2 = by1 + text_h + (pad_y * 2)

            # Assert badge does not intersect safe zone
            if not self.is_box_safe((bx1, by1, bx2, by2)):
                raise SafeZoneViolationError("Tension badge intersects YouTube safe zone!")

            # Draw rounded pill badge with outline
            draw.rounded_rectangle(
                [bx1, by1, bx2, by2],
                radius=14,
                fill=theme.badge_bg,
                outline=theme.highlight_accent,
                width=3,
            )
            draw.text((bx1 + pad_x, by1 + pad_y - 2), badge_text, font=badge_font, fill=theme.badge_text)

        # 4. Draw Hook Text (High Contrast with Stroke & Shadow)
        # Position constrained to upper/middle-left: X in [90, width*0.75], Y in [200, height*0.70]
        max_allowed_x = int(self.width * 0.76)
        max_allowed_y = int(self.height * 0.72)

        font_size = 92
        font = self._get_best_font(size=font_size)

        # Word wrap hook text to avoid extending into the safe zone
        lines = self._wrap_text(hook_text, font, max_allowed_x - 90, draw)

        start_y = 230 if tension_badge else 160
        line_spacing = int(font_size * 1.25)

        # Verify full text block bounding box
        total_text_h = len(lines) * line_spacing
        text_bbox = (90, start_y, max_allowed_x, start_y + total_text_h)

        if not self.is_box_safe(text_bbox) or (start_y + total_text_h) > max_allowed_y:
            # If text is too tall, decrease font size to fit safely
            font_size = 72
            font = self._get_best_font(size=font_size)
            line_spacing = int(font_size * 1.22)
            lines = self._wrap_text(hook_text, font, max_allowed_x - 90, draw)
            start_y = 210 if tension_badge else 140

        current_y = start_y
        for i, line in enumerate(lines):
            # Highlight first line or last line with accent color
            line_color = theme.highlight_accent if (i == 0 or i == len(lines) - 1) else theme.text_color
            self._draw_stroked_text(
                draw=draw,
                pos=(90, current_y),
                text=line,
                font=font,
                fill=line_color,
                stroke_fill=theme.stroke_color,
                stroke_width=6,
            )
            current_y += line_spacing

        # 5. Output resolution and export
        if output_path is None:
            output_path = Path("thumbnail.jpg")
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        canvas.save(output_path, "JPEG", quality=95)
        logger.info(f"Generated counterpoint thumbnail at {output_path} ({self.width}x{self.height})")
        return output_path

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
    ) -> List[str]:
        """Splits text into wrapped lines that strictly respect max_width."""
        words = text.split()
        lines: List[str] = []
        current_line: List[str] = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
        return lines or [text]

    def _draw_stroked_text(
        self,
        draw: ImageDraw.ImageDraw,
        pos: Tuple[int, int],
        text: str,
        font: ImageFont.ImageFont,
        fill: Tuple[int, int, int],
        stroke_fill: Tuple[int, int, int],
        stroke_width: int = 4,
    ) -> None:
        """Renders high-visibility text with thick drop shadow and outer stroke."""
        x, y = pos
        # Drop shadow offset
        shadow_offset = stroke_width + 3
        draw.text(
            (x + shadow_offset, y + shadow_offset),
            text,
            font=font,
            fill=(0, 0, 0),
        )
        # Text with stroke
        draw.text(
            (x, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

    def render_safe_zone_overlay(
        self,
        image_or_path: Union[Image.Image, Path, str],
        output_path: Optional[Union[Path, str]] = None,
    ) -> Image.Image:
        """
        Renders a semi-transparent diagnostic overlay demonstrating the YouTube
        duration timestamp safe zone for UI inspection (VAC-UI-04).
        """
        if isinstance(image_or_path, (str, Path)):
            base = Image.open(image_or_path).convert("RGBA")
        else:
            base = image_or_path.convert("RGBA")

        # Target dimensions match base
        w, h = base.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        safe = SafeZoneRect(
            x1=int(w * (1.0 - self.safe_zone_width_ratio)),
            y1=int(h * (1.0 - self.safe_zone_height_ratio)),
            x2=w,
            y2=h,
        )

        # Forbidden zone: Semi-transparent alert red box
        draw.rectangle(
            [safe.x1, safe.y1, safe.x2, safe.y2],
            fill=(239, 68, 68, 120),  # Alert Crimson 47% opacity
            outline=(255, 255, 255, 230),
            width=3,
        )

        # Draw mock YouTube timestamp badge (e.g., '14:20')
        badge_pad_x = 18
        badge_pad_y = 10
        badge_w = int(safe.width * 0.6)
        badge_h = int(safe.height * 0.45)
        bx1 = safe.x1 + (safe.width - badge_w) // 2
        by1 = safe.y1 + (safe.height - badge_h) // 2
        bx2 = bx1 + badge_w
        by2 = by1 + badge_h

        draw.rounded_rectangle(
            [bx1, by1, bx2, by2],
            radius=10,
            fill=(0, 0, 0, 230),
            outline=(255, 255, 255, 180),
            width=2,
        )

        font = self._get_best_font(size=28)
        draw.text((bx1 + 22, by1 + 10), "14:20", font=font, fill=(255, 255, 255, 255))

        # Safe area label
        lbl_font = self._get_best_font(size=20)
        draw.text(
            (safe.x1 + 15, safe.y1 + 12),
            "YOUTUBE BADGE ZONE",
            font=lbl_font,
            fill=(255, 255, 255, 240),
        )

        result = Image.alpha_composite(base, overlay).convert("RGB")
        if output_path:
            output_path = Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(output_path, "JPEG", quality=90)

        return result

    def verify_safe_zone_clearance(
        self,
        image_or_path: Union[Image.Image, Path, str],
        expected_uniform_threshold: float = 0.90,
    ) -> Dict[str, Union[bool, float, str]]:
        """
        Diagnostic verification: Checks if the safe zone contains unexpected sharp
        content or text by comparing edge energy / high-frequency details.
        """
        if isinstance(image_or_path, (str, Path)):
            img = Image.open(image_or_path).convert("L")
        else:
            img = image_or_path.convert("L")

        safe = self.get_safe_zone()
        crop_safe = img.crop((safe.x1, safe.y1, safe.x2, safe.y2))

        # Apply edge detection filter
        edges = crop_safe.filter(ImageFilter.FIND_EDGES)
        # Pillow 12+ get_flattened_data or fallback
        if hasattr(edges, "get_flattened_data"):
            data = edges.get_flattened_data()
        else:
            data = edges.getdata()
        avg_edge_intensity = sum(data) / (edges.width * edges.height)

        # A clear safe zone with only soft gradient or background has low edge intensity
        is_clear = avg_edge_intensity < 25.0

        return {
            "safe_zone_rect": (safe.x1, safe.y1, safe.x2, safe.y2),
            "avg_edge_intensity": round(avg_edge_intensity, 2),
            "is_clear": is_clear,
            "status": "CLEAR" if is_clear else "POTENTIAL_OBSTRUCTION",
        }
