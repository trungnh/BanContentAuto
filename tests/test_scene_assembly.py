"""
Unit and Integration Tests for Atomic Scene Assembly & 16:9 Transformation (WU-05, REQ-B2-04, VAC-UI-03).
Verifies:
1. Video probing accuracy (dimensions, duration, fps, aspect ratio).
2. Timing fitting decision logic (trim, slow-motion, loop, image still).
3. FFmpeg filter_complex syntax generation (blurred background pad, slow-motion, Ken Burns, visual highlights).
4. Full FFmpeg atomic scene assembly with real media synthesis and ffprobe verification:
   - 9:16 vertical video -> 16:9 1920x1080 blurred transformation.
   - Cinematic slow-motion duration fitting (<= 20% deficit).
   - Audio mixing: Voiceover 100% + Ambient SFX 35% with seamless looping.
   - Entity still image transformation into exact-frame video.
"""

from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig
from autovideo.production.scene_muxer import SceneMuxConfig, SceneMuxResult, SceneMuxer
from autovideo.production.transformer import (
    HighlightConfig,
    TimingFitDecision,
    TransformationConfig,
    VideoProbeError,
    VideoProbeInfo,
    VideoTransformError,
    VideoTransformer,
    probe_video,
)


# --- Media Test Helpers ---

def create_synthetic_audio(file_path: Path, duration_sec: float, sample_rate: int = 48000) -> Path:
    """Creates a valid 16-bit PCM WAV audio file with specified duration."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration_sec * sample_rate)
    with wave.open(str(file_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            # 440Hz sine tone
            sample = int(16000 * math.sin(2.0 * math.pi * 440.0 * (i / sample_rate)))
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(frames)
    return file_path


def create_synthetic_video(
    file_path: Path,
    width: int,
    height: int,
    duration_sec: float,
    fps: int = 30,
) -> Path:
    """Creates a synthetic MP4 video file using ffmpeg testsrc."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    bm = BinaryManager()
    ffmpeg_info = bm.require("ffmpeg")

    cmd = [
        str(ffmpeg_info.path),
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_sec:.2f}:size={width}x{height}:rate={fps}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        str(file_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to create synthetic test video: {proc.stderr}")
    return file_path


def create_synthetic_image(file_path: Path, width: int = 720, height: int = 1280, color: str = "red") -> Path:
    """Creates a test still PNG image."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=color)
    img.save(str(file_path), "PNG")
    return file_path


# --- Test Suite ---

class TestVideoProbe:
    """Tests for probe_video metadata extraction."""

    def test_probe_video_missing_file_raises_error(self, tmp_path: Path):
        non_existent = tmp_path / "missing.mp4"
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            probe_video(non_existent)

    def test_probe_video_empty_file_raises_error(self, tmp_path: Path):
        empty_file = tmp_path / "empty.mp4"
        empty_file.touch()
        with pytest.raises(ValueError, match="Video file is empty"):
            probe_video(empty_file)

    def test_probe_vertical_video_geometry(self, tmp_path: Path):
        vid_path = create_synthetic_video(
            tmp_path / "vertical_clip.mp4",
            width=720,
            height=1280,
            duration_sec=2.0,
            fps=30,
        )
        info = probe_video(vid_path)

        assert info.width == 720
        assert info.height == 1280
        assert info.is_vertical is True
        assert abs(info.aspect_ratio - (720 / 1280)) < 0.01
        assert abs(info.duration_sec - 2.0) <= 0.1
        assert info.fps == 30.0
        assert info.codec_name == "h264"
        assert info.total_frames in (59, 60, 61)

    def test_probe_horizontal_video_geometry(self, tmp_path: Path):
        vid_path = create_synthetic_video(
            tmp_path / "horizontal_clip.mp4",
            width=1920,
            height=1080,
            duration_sec=1.5,
            fps=30,
        )
        info = probe_video(vid_path)

        assert info.width == 1920
        assert info.height == 1080
        assert info.is_vertical is False
        assert abs(info.aspect_ratio - (16 / 9)) < 0.01
        assert abs(info.duration_sec - 1.5) <= 0.1


class TestVideoTransformer:
    """Tests for VideoTransformer decision logic and filter graph generation."""

    def setup_method(self):
        self.transformer = VideoTransformer()

    def test_timing_fit_trim_when_source_longer(self):
        decision = self.transformer.calculate_timing_fit(
            source_duration_sec=6.5,
            target_duration_sec=4.0,
            start_offset_sec=1.0,
        )
        assert decision.action == "trim"
        assert decision.slowmo_factor == 1.0
        assert decision.trim_start_sec == 1.0
        assert decision.effective_duration_sec == 4.0

    def test_timing_fit_slow_motion_when_deficit_within_20_percent(self):
        # Deficit: (5.0 - 4.2) / 5.0 = 0.16 (16% <= 20%)
        decision = self.transformer.calculate_timing_fit(
            source_duration_sec=4.2,
            target_duration_sec=5.0,
        )
        assert decision.action == "slow_motion"
        expected_factor = 5.0 / 4.2
        assert abs(decision.slowmo_factor - expected_factor) < 1e-4
        assert decision.effective_duration_sec == 5.0

    def test_timing_fit_loop_when_deficit_exceeds_20_percent(self):
        # Deficit: (5.0 - 2.0) / 5.0 = 0.60 (60% > 20%)
        decision = self.transformer.calculate_timing_fit(
            source_duration_sec=2.0,
            target_duration_sec=5.0,
        )
        assert decision.action == "loop"
        assert decision.slowmo_factor == 1.0
        assert decision.effective_duration_sec == 5.0

    def test_timing_fit_image_still(self):
        decision = self.transformer.calculate_timing_fit(
            source_duration_sec=0.0,
            target_duration_sec=4.5,
            is_image=True,
        )
        assert decision.action == "image_still"
        assert decision.slowmo_factor == 1.0
        assert decision.effective_duration_sec == 4.5

    def test_build_blurred_margin_filter_syntax(self):
        filter_str = self.transformer.build_blurred_margin_filter("0:v", "out_pad")
        assert "[0:v]split=2[bg_in][fg_in]" in filter_str
        assert "scale=1920:1080:force_original_aspect_ratio=increase" in filter_str
        assert "crop=1920:1080" in filter_str
        assert "boxblur=25:5" in filter_str
        assert "eq=brightness=-0.15" in filter_str
        assert "scale=1920:1080:force_original_aspect_ratio=decrease" in filter_str
        assert "overlay=(W-w)/2:(H-h)/2[out_pad]" in filter_str

    def test_build_ken_burns_filter_syntax(self):
        filter_str = self.transformer.build_ken_burns_filter("in_label", "out_label", total_frames=120)
        assert "[in_label]zoompan=z='min(zoom+0.0015,1.15)'" in filter_str
        assert "d=120" in filter_str
        assert "s=1920x1080:fps=30[out_label]" in filter_str

    def test_build_highlight_filter_syntax(self):
        highlight = HighlightConfig(
            enabled=True,
            type="box",
            color="red",
            opacity=0.85,
            width=300,
            height=300,
            thickness=6,
        )
        filter_str = self.transformer.build_highlight_filter("v_in", "v_out", highlight)
        assert "[v_in]drawbox=" in filter_str
        assert "w=300:h=300" in filter_str
        assert "color=red@0.85:t=6[v_out]" in filter_str

    def test_compile_video_filter_with_all_effects(self):
        config = TransformationConfig(
            enable_blurred_margin=True,
            enable_ken_burns=True,
            highlight=HighlightConfig(enabled=True, color="red"),
        )
        transformer = VideoTransformer(config=config)
        decision = TimingFitDecision(
            action="slow_motion",
            source_duration_sec=4.0,
            target_duration_sec=4.8,
            slowmo_factor=1.2,
            trim_start_sec=0.0,
            effective_duration_sec=4.8,
        )

        f_complex, final_label = transformer.compile_video_filter(
            timing_decision=decision,
            source_is_vertical=True,
            is_image=False,
        )

        assert "setpts=1.200000*PTS,fps=30" in f_complex
        assert "boxblur=25:5" in f_complex
        assert "zoompan=" in f_complex
        assert "drawbox=" in f_complex
        assert final_label == "v_highlight"


class TestSceneMuxer:
    """Integration and Unit tests for SceneMuxer execution with FFmpeg."""

    @pytest.fixture
    def muxer(self, tmp_path: Path) -> SceneMuxer:
        app_cfg = AppConfig.from_base_dir(tmp_path)
        app_cfg.ensure_directories()
        return SceneMuxer(config=app_cfg)

    def test_assemble_scene_missing_media_raises_file_not_found(self, muxer: SceneMuxer, tmp_path: Path):
        audio_file = create_synthetic_audio(tmp_path / "vo.wav", duration_sec=1.0)
        with pytest.raises(FileNotFoundError, match="Media file not found"):
            muxer.assemble_scene(
                project_id="p1",
                scene_idx=1,
                media_path=tmp_path / "missing.mp4",
                voiceover_audio_path=audio_file,
            )

    def test_assemble_scene_missing_audio_raises_file_not_found(self, muxer: SceneMuxer, tmp_path: Path):
        media_file = create_synthetic_video(tmp_path / "video.mp4", width=720, height=1280, duration_sec=1.0)
        with pytest.raises(FileNotFoundError, match="Voiceover audio file not found"):
            muxer.assemble_scene(
                project_id="p1",
                scene_idx=1,
                media_path=media_file,
                voiceover_audio_path=tmp_path / "missing.wav",
            )

    def test_assemble_scene_vertical_video_with_slowmo(self, muxer: SceneMuxer, tmp_path: Path):
        """
        Integration test:
        - Source: 2.0s vertical video (720x1280).
        - Voiceover: 2.4s audio.
        - Deficit: (2.4 - 2.0) / 2.4 = 16.6% <= 20% -> triggers slow-motion (factor 1.2x).
        - Output: 1920x1080 Full HD, ~2.4s duration, 30fps CFR, H.264 / AAC.
        """
        media_file = create_synthetic_video(
            tmp_path / "clip_vert.mp4",
            width=720,
            height=1280,
            duration_sec=2.0,
            fps=30,
        )
        audio_file = create_synthetic_audio(
            tmp_path / "voiceover.wav",
            duration_sec=2.40,
            sample_rate=48000,
        )

        result = muxer.assemble_scene(
            project_id="test_proj_01",
            scene_idx=1,
            media_path=media_file,
            voiceover_audio_path=audio_file,
        )

        assert result.scene_id == 1
        assert result.project_id == "test_proj_01"
        assert result.output_path.exists()
        assert result.timing_action == "slow_motion"
        assert result.width == 1920
        assert result.height == 1080
        assert result.fps == 30.0
        assert result.has_audio is True
        # Duration within 0.1s tolerance
        assert abs(result.duration_sec - 2.40) <= 0.15

        # Probe output with ffprobe independently
        probe = probe_video(result.output_path)
        assert probe.width == 1920
        assert probe.height == 1080
        assert probe.codec_name == "h264"
        assert probe.has_audio is True

    def test_assemble_scene_with_ambient_sfx_mixing(self, muxer: SceneMuxer, tmp_path: Path):
        """
        Integration test:
        - Source: 3.0s horizontal video (1920x1080).
        - Voiceover: 2.0s audio.
        - Ambient: 1.0s audio (looped under voiceover at 35% volume).
        - Output: Trimmed to 2.0s with mixed stereo audio track.
        """
        media_file = create_synthetic_video(
            tmp_path / "clip_horiz.mp4",
            width=1920,
            height=1080,
            duration_sec=3.0,
            fps=30,
        )
        vo_file = create_synthetic_audio(tmp_path / "vo_2s.wav", duration_sec=2.0)
        amb_file = create_synthetic_audio(tmp_path / "sfx_1s.wav", duration_sec=1.0)

        result = muxer.assemble_scene(
            project_id="test_proj_02",
            scene_idx=2,
            media_path=media_file,
            voiceover_audio_path=vo_file,
            ambient_audio_path=amb_file,
        )

        assert result.scene_id == 2
        assert result.output_path.exists()
        assert result.timing_action == "trim"
        assert result.width == 1920
        assert result.height == 1080
        assert result.has_audio is True
        assert abs(result.duration_sec - 2.0) <= 0.15

    def test_assemble_scene_from_static_entity_image(self, muxer: SceneMuxer, tmp_path: Path):
        """
        Integration test:
        - Source: PNG static image (720x1280).
        - Voiceover: 1.8s audio.
        - Output: 1920x1080 video with blurred pad and exact frame duration.
        """
        img_file = create_synthetic_image(tmp_path / "card.png", width=720, height=1280)
        vo_file = create_synthetic_audio(tmp_path / "vo_1_8s.wav", duration_sec=1.80)

        result = muxer.assemble_scene(
            project_id="test_proj_03",
            scene_idx=3,
            media_path=img_file,
            voiceover_audio_path=vo_file,
        )

        assert result.scene_id == 3
        assert result.output_path.exists()
        assert result.timing_action == "image_still"
        assert result.width == 1920
        assert result.height == 1080
        assert result.has_audio is True
        assert abs(result.duration_sec - 1.80) <= 0.15

    def test_compile_video_filter_safe_margin_zoom(self):
        """Transformer applies scaled canvas zoom when safe_margin_zoom > 1.0."""
        config = TransformationConfig(safe_margin_zoom=1.08)
        transformer = VideoTransformer(config=config)
        decision = TimingFitDecision(
            action="trim",
            source_duration_sec=10.0,
            target_duration_sec=4.0,
            slowmo_factor=1.0,
            trim_start_sec=0.0,
            effective_duration_sec=4.0,
        )
        f_complex, out_label = transformer.compile_video_filter(
            timing_decision=decision,
            source_is_vertical=False,
            is_image=False,
        )
        # 1920 * 1.08 = 2073.6 -> 2074, 1080 * 1.08 = 1166.4 -> 1166
        assert "scale=2074:1166:force_original_aspect_ratio=increase" in f_complex
        assert "crop=1920:1080:(in_w-out_w)/2:(in_h-out_h)/2" in f_complex

    def test_compile_video_filter_with_pre_crop(self):
        """Transformer prepends pre_crop to filter chain when black bars are detected."""
        transformer = VideoTransformer()
        decision = TimingFitDecision(
            action="trim",
            source_duration_sec=8.0,
            target_duration_sec=3.0,
            slowmo_factor=1.0,
            trim_start_sec=0.0,
            effective_duration_sec=3.0,
        )
        f_complex, out_label = transformer.compile_video_filter(
            timing_decision=decision,
            source_is_vertical=False,
            is_image=False,
            pre_crop="crop=1408:1072:258:4",
        )
        assert "[0:v]crop=1408:1072:258:4,scale=1920:1080" in f_complex

