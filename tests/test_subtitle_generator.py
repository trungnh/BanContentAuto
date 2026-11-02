"""
Unit tests for SubtitleGenerator (ASS, SRT, chunking, presets).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autovideo.production.subtitle_generator import (
    SUBTITLE_PRESETS,
    SubtitleCue,
    SubtitleGenerator,
    build_cues_from_scenes,
    format_ass_timestamp,
    format_srt_timestamp,
    split_text_into_chunks,
)


def test_format_ass_timestamp():
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(1.5) == "0:00:01.50"
    assert format_ass_timestamp(65.25) == "0:01:05.25"
    assert format_ass_timestamp(3661.05) == "1:01:01.05"


def test_format_srt_timestamp():
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(1.5) == "00:00:01,500"
    assert format_srt_timestamp(65.25) == "00:01:05,250"
    assert format_srt_timestamp(3661.05) == "01:01:01,050"


def test_split_text_into_chunks_short():
    text = "Linh cẩu đốm là loài săn mồi đáng sợ."
    chunks = split_text_into_chunks(text, max_words_per_chunk=9)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_into_chunks_punctuation():
    text = (
        "Một nghìn một trăm psi lực cắn, đủ sức nghiền nát ống xương đùi hươu cao cổ "
        "chỉ sau một cú siết hàm duy nhất."
    )
    chunks = split_text_into_chunks(text, max_words_per_chunk=8)
    assert len(chunks) >= 2
    assert "Một nghìn một trăm psi lực cắn," in chunks[0]
    # Check that total words preserved
    total_words_orig = set(text.replace(",", "").split())
    total_words_chunked = set(" ".join(chunks).replace(",", "").split())
    assert total_words_orig == total_words_chunked


def test_build_cues_from_scenes():
    mock_scenes = [
        MagicMock(
            scene_id="SCENE_001",
            text="Linh cẩu đốm là loài săn mồi đỉnh cao của châu Phi.",
            duration_sec=4.0,
        ),
        MagicMock(
            scene_id="SCENE_002",
            text="Chúng sở hữu cơ hàm vô cùng mạnh mẽ, có thể nhai nát cả xương cứng.",
            duration_sec=6.0,
        ),
    ]

    cues = build_cues_from_scenes(mock_scenes, max_words_per_chunk=8)
    assert len(cues) >= 2
    # Verify sequential timestamps
    for i in range(len(cues) - 1):
        assert cues[i].start_sec < cues[i].end_sec
        assert cues[i].end_sec <= cues[i + 1].start_sec + 0.05
    # Total duration should match scene sum
    assert cues[-1].end_sec <= 10.1


def test_generate_ass_and_srt(tmp_path):
    cues = [
        SubtitleCue(start_sec=0.0, end_sec=3.5, text="Phân đoạn mở đầu tài liệu"),
        SubtitleCue(start_sec=3.5, end_sec=7.0, text="Khám phá sức mạnh linh cẩu"),
    ]

    ass_path = tmp_path / "test.ass"
    srt_path = tmp_path / "test.srt"

    SubtitleGenerator.generate_ass(cues, ass_path, preset_id="cinematic_white")
    SubtitleGenerator.generate_srt(cues, srt_path)

    assert ass_path.exists()
    assert srt_path.exists()

    ass_content = ass_path.read_text(encoding="utf-8")
    assert "[Script Info]" in ass_content
    assert "[V4+ Styles]" in ass_content
    assert "PlayResX: 1920" in ass_content
    assert "Dialogue: 0,0:00:00.00,0:00:03.50,Default" in ass_content
    assert "Phân đoạn mở đầu tài liệu" in ass_content

    srt_content = srt_path.read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:03,500\nPhân đoạn mở đầu tài liệu" in srt_content
    assert "2\n00:00:03,500 --> 00:00:07,000\nKhám phá sức mạnh linh cẩu" in srt_content


def test_all_presets_valid():
    for p_id, p_data in SUBTITLE_PRESETS.items():
        preset = SubtitleGenerator.get_preset(p_id)
        assert "font_name" in preset
        assert "font_size" in preset
        assert "primary_color" in preset
        assert "outline_color" in preset
        assert preset["alignment"] == 2


def test_generate_ass_custom_margin_v(tmp_path):
    cues = [
        SubtitleCue(start_sec=0.0, end_sec=2.0, text="Test custom margin"),
    ]
    ass_path = tmp_path / "custom_margin.ass"
    SubtitleGenerator.generate_ass(cues, ass_path, preset_id="cinematic_white", custom_margin_v=85)
    content = ass_path.read_text(encoding="utf-8")
    assert "40,40,85,1" in content
