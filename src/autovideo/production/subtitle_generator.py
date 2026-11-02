"""
Subtitle Generator & Burner Module (ASS & SRT).
Supports Cinematic Classic, Yellow Spotlight, and Boxed Translucent presets.
"""

from __future__ import annotations

import logging
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Presets Configuration
# ---------------------------------------------------------------------------

SUBTITLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "cinematic_white": {
        "id": "cinematic_white",
        "name": "🎬 Phim Tài Liệu Chuẩn (Cinematic White)",
        "font_name": "Montserrat",
        "fallback_font": "Arial",
        "font_size": 22,
        "primary_color": "&H00FFFFFF",   # Pure White in ASS BGR format
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",   # Solid Black Outline
        "back_color": "&H80000000",      # 50% Translucent Shadow
        "bold": 1,
        "italic": 0,
        "border_style": 1,               # 1 = Outline with drop shadow
        "outline": 2.4,
        "shadow": 1.2,
        "alignment": 2,                  # 2 = Bottom-center
        "margin_l": 40,
        "margin_r": 40,
        "margin_v": 55,                  # 55px from bottom (Safe Zone)
    },
    "yellow_spotlight": {
        "id": "yellow_spotlight",
        "name": "🌟 Kênh Khám Phá Nổi Bật (Yellow Spotlight)",
        "font_name": "Montserrat",
        "fallback_font": "Arial Black",
        "font_size": 24,
        "primary_color": "&H0000E6FF",   # Bright Vivid Yellow (&H00<BB><GG><RR>)
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",   # Bold Black Outline
        "back_color": "&H00000000",
        "bold": 1,
        "italic": 0,
        "border_style": 1,
        "outline": 3.4,
        "shadow": 0.0,
        "alignment": 2,
        "margin_l": 40,
        "margin_r": 40,
        "margin_v": 55,
    },
    "boxed_translucent": {
        "id": "boxed_translucent",
        "name": "📦 Hộp Nền Bán Trong Suốt (Boxed Translucent)",
        "font_name": "Montserrat",
        "fallback_font": "Arial",
        "font_size": 22,
        "primary_color": "&H00FFFFFF",   # Pure White text
        "secondary_color": "&H000000FF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",      # ~60% Dark Translucent Background Box
        "bold": 1,
        "italic": 0,
        "border_style": 3,               # 3 = Opaque/Translucent Bounding Box
        "outline": 5.0,                  # Box padding
        "shadow": 0.0,
        "alignment": 2,
        "margin_l": 40,
        "margin_r": 40,
        "margin_v": 55,
    },
}


@dataclass
class SubtitleCue:
    """Represents a single timed subtitle line."""
    start_sec: float
    end_sec: float
    text: str


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def format_ass_timestamp(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc (centiseconds)."""
    seconds = max(0.0, seconds)
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = int(rem % 60)
    cs = int(round((rem - int(rem)) * 100))
    if cs >= 100:
        cs = 0
        secs += 1
        if secs >= 60:
            secs = 0
            mins += 1
            if mins >= 60:
                mins = 0
                hrs += 1
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm (milliseconds)."""
    seconds = max(0.0, seconds)
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = int(rem % 60)
    ms = int(round((rem - int(rem)) * 1000))
    if ms >= 1000:
        ms = 0
        secs += 1
        if secs >= 60:
            secs = 0
            mins += 1
            if mins >= 60:
                mins = 0
                hrs += 1
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def split_text_into_chunks(text: str, max_words_per_chunk: int = 9) -> List[str]:
    """
    Splits a longer sentence into natural, readable subtitle chunks.
    Breaks by punctuation first (, . ; : ! ? -), then by word count.
    """
    clean_text = " ".join(text.strip().split())
    if not clean_text:
        return []

    words = clean_text.split()
    if len(words) <= max_words_per_chunk:
        return [clean_text]

    # Split by natural clause delimiters while keeping separators attached
    raw_clauses = re.split(r"([,.;:!?—–]+)", clean_text)
    clauses: List[str] = []
    i = 0
    while i < len(raw_clauses):
        part = raw_clauses[i].strip()
        if i + 1 < len(raw_clauses) and re.match(r"^[,.;:!?—–]+$", raw_clauses[i + 1].strip()):
            part += raw_clauses[i + 1].strip()
            i += 2
        else:
            i += 1
        if part:
            clauses.append(part)

    # Recombine small clauses or split extra-large clauses
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_words = 0

    for clause in clauses:
        clause_words = clause.split()
        if len(clause_words) > max_words_per_chunk:
            # Clause itself is too long -> flush current and split clause by word limit
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_words = 0
            for start_idx in range(0, len(clause_words), max_words_per_chunk):
                sub = clause_words[start_idx : start_idx + max_words_per_chunk]
                chunks.append(" ".join(sub))
        elif current_words + len(clause_words) <= max_words_per_chunk:
            current_chunk.append(clause)
            current_words += len(clause_words)
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [clause]
            current_words = len(clause_words)

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks if chunks else [clean_text]


def build_cues_from_scenes(
    scenes: List[Any],
    max_words_per_chunk: int = 9,
) -> List[SubtitleCue]:
    """
    Builds timed SubtitleCue objects across a list of scenes.
    Allocates scene duration proportionally across chunks based on word count.
    """
    cues: List[SubtitleCue] = []
    cumulative_time = 0.0

    for s in scenes:
        text = getattr(s, "text", "") or (s.get("text", "") if isinstance(s, dict) else "")
        dur = float(getattr(s, "duration_sec", 0.0) or (s.get("duration_sec", 0.0) if isinstance(s, dict) else 0.0))
        if dur <= 0.0:
            dur = 4.0

        chunks = split_text_into_chunks(text, max_words_per_chunk=max_words_per_chunk)
        if not chunks:
            cumulative_time += dur
            continue

        total_words = sum(len(c.split()) for c in chunks) or len(chunks)
        chunk_offset = 0.0

        for idx, chunk in enumerate(chunks):
            w_count = len(chunk.split())
            if idx == len(chunks) - 1:
                # Last chunk absorbs any floating point remainder
                chunk_dur = max(0.4, dur - chunk_offset)
            else:
                ratio = w_count / total_words
                chunk_dur = max(0.6, dur * ratio)
                # Keep headroom for remaining chunks
                remaining_chunks = len(chunks) - 1 - idx
                if chunk_offset + chunk_dur + (remaining_chunks * 0.4) > dur:
                    chunk_dur = max(0.4, (dur - chunk_offset) / (remaining_chunks + 1))

            start_t = cumulative_time + chunk_offset
            end_t = start_t + chunk_dur
            cues.append(SubtitleCue(start_sec=start_t, end_sec=end_t, text=chunk))
            chunk_offset += chunk_dur

        cumulative_time += dur

    return cues


# ---------------------------------------------------------------------------
# Subtitle File Writers
# ---------------------------------------------------------------------------

class SubtitleGenerator:
    """Generates styled ASS and standard SRT subtitle files, and handles burn-in via FFmpeg."""

    @classmethod
    def get_preset(cls, preset_id: str) -> Dict[str, Any]:
        """Resolves preset configuration dictionary by ID."""
        return SUBTITLE_PRESETS.get(preset_id, SUBTITLE_PRESETS["cinematic_white"])

    @classmethod
    def generate_ass(
        cls,
        cues: List[SubtitleCue],
        output_path: Path,
        preset_id: str = "cinematic_white",
        custom_font: Optional[str] = None,
        custom_size: Optional[int] = None,
        custom_margin_v: Optional[int] = None,
    ) -> Path:
        """
        Generates a 1080p ASS (Advanced SubStation Alpha) file with typography styles.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        preset = cls.get_preset(preset_id)

        font_name = custom_font or preset["font_name"]
        font_size = custom_size or preset["font_size"]
        primary = preset["primary_color"]
        secondary = preset["secondary_color"]
        outline = preset["outline_color"]
        back = preset["back_color"]
        bold = preset["bold"]
        italic = preset["italic"]
        border_style = preset["border_style"]
        outline_w = preset["outline"]
        shadow_w = preset["shadow"]
        alignment = preset["alignment"]
        margin_l = preset["margin_l"]
        margin_r = preset["margin_r"]
        margin_v = custom_margin_v if custom_margin_v is not None else preset["margin_v"]

        lines = [
            "[Script Info]",
            "Title: BanContentAuto Styled Subtitles",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{font_size},{primary},{secondary},{outline},{back},"
            f"{bold},{italic},0,0,100,100,0,0,{border_style},{outline_w},{shadow_w},{alignment},"
            f"{margin_l},{margin_r},{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for cue in cues:
            start_str = format_ass_timestamp(cue.start_sec)
            end_str = format_ass_timestamp(cue.end_sec)
            # Escape ASS special braces
            safe_text = cue.text.replace("{", "\\{").replace("}", "\\}")
            lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{safe_text}")

        content = "\n".join(lines) + "\n"
        output_path.write_text(content, encoding="utf-8")
        logger.info("Generated ASS subtitles (%d cues) at %s", len(cues), output_path)
        return output_path

    @classmethod
    def generate_srt(
        cls,
        cues: List[SubtitleCue],
        output_path: Path,
    ) -> Path:
        """
        Generates standard UTF-8 SRT file for YouTube CC upload or media player soft-subs.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        blocks = []

        for idx, cue in enumerate(cues, start=1):
            start_str = format_srt_timestamp(cue.start_sec)
            end_str = format_srt_timestamp(cue.end_sec)
            blocks.append(f"{idx}\n{start_str} --> {end_str}\n{cue.text}\n")

        content = "\n".join(blocks)
        output_path.write_text(content, encoding="utf-8")
        logger.info("Generated SRT subtitles (%d cues) at %s", len(cues), output_path)
        return output_path

    @classmethod
    def generate_subtitles_for_scenes(
        cls,
        scenes: List[Any],
        output_base_path: Path,
        preset_id: str = "cinematic_white",
        custom_font: Optional[str] = None,
        custom_size: Optional[int] = None,
        custom_margin_v: Optional[int] = None,
    ) -> Tuple[Path, Path]:
        """
        Convenience method: generates both .ass and .srt files for a list of scenes.
        Returns (ass_path, srt_path).
        """
        cues = build_cues_from_scenes(scenes)
        ass_path = output_base_path.with_suffix(".ass")
        srt_path = output_base_path.with_suffix(".srt")

        cls.generate_ass(
            cues=cues,
            output_path=ass_path,
            preset_id=preset_id,
            custom_font=custom_font,
            custom_size=custom_size,
            custom_margin_v=custom_margin_v,
        )
        cls.generate_srt(cues=cues, output_path=srt_path)
        return ass_path, srt_path

    @classmethod
    def burn_subtitles_to_video(
        cls,
        input_video_path: Path,
        subtitle_ass_path: Path,
        output_video_path: Path,
        ffmpeg_bin: str = "ffmpeg",
        crf: int = 20,
        preset: str = "veryfast",
    ) -> Path:
        """
        Burns styled subtitles from an ASS file into the target video using FFmpeg.
        Audio is copied directly (-c:a copy) to preserve fidelity and zero re-encode delay.
        """
        if not input_video_path.is_file():
            raise FileNotFoundError(f"Input video not found: {input_video_path}")
        if not subtitle_ass_path.is_file():
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_ass_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        # Escape path for FFmpeg subtitles filter on Windows: forward slashes & escaped colon
        clean_sub = str(subtitle_ass_path.resolve()).replace("\\", "/").replace(":", "\\:")

        cmd = [
            str(ffmpeg_bin),
            "-y",
            "-i", str(input_video_path),
            "-vf", f"subtitles='{clean_sub}'",
            "-c:v", "libx264",
            "-preset", str(preset),
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_video_path),
        ]

        logger.info("Burning subtitles via FFmpeg into %s...", output_video_path.name)
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0 or not output_video_path.exists():
            logger.error("FFmpeg burn subtitles failed: %s", res.stderr[-500:])
            raise RuntimeError(f"FFmpeg burn subtitles failed: {res.stderr[-300:]}")

        logger.info("Successfully burned subtitles into %s", output_video_path)
        return output_video_path
