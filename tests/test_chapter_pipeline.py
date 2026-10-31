"""
Unit and Integration Tests for Modular Chapter Builder & Concat Demuxer (WU-06).
Covers:
1. RollingDiskBuffer: Directory size measurement, limit safety check, atomic scene cleanup, proactive purging.
2. ConcatDemuxer: Concat manifest generation, escaping, zero-reencode concatenation (-c copy), post-verification.
3. PipelineCheckpoint: Durability, atomic file writing, checkpoint recovery.
4. ChapterBuilder: Modular assembly, immediate rolling buffer release, resume skipping.
5. Full End-to-End Pipeline: Multi-chapter production, real FFmpeg zero-reencode concat, fault-tolerant resume.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig
from autovideo.production.chapter_builder import (
    ChapterBuilder,
    ChapterBuilderError,
    ChapterRenderResult,
    PipelineCheckpoint,
    ProductionPipeline,
    ProductionResult,
    SceneAssets,
)
from autovideo.production.concat_demuxer import (
    ConcatDemuxer,
    ConcatDemuxerError,
    ConcatResult,
)
from autovideo.production.rolling_buffer import RollingDiskBuffer
from autovideo.production.scene_muxer import SceneMuxConfig, SceneMuxResult, SceneMuxer
from autovideo.production.transformer import VideoProbeInfo, probe_video
from autovideo.script.pipeline import Chapter, Scene, Screenplay


# --- Test Helpers for Synthetic Media ---

def create_test_wav(file_path: Path, duration_sec: float, sample_rate: int = 48000) -> Path:
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


def create_test_mp4(
    file_path: Path,
    width: int = 1920,
    height: int = 1080,
    duration_sec: float = 1.0,
    fps: int = 30,
) -> Path:
    """Creates a synthetic MP4 video file using ffmpeg testsrc with silent audio."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    bm = BinaryManager()
    ffmpeg_info = bm.require("ffmpeg")

    cmd = [
        str(ffmpeg_info.path),
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_sec:.2f}:size={width}x{height}:rate={fps}",
        "-f", "lavfi",
        "-i", f"anullsrc=r=48000:cl=stereo",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{duration_sec:.2f}",
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


# --- 1. Tests for RollingDiskBuffer ---

class TestRollingDiskBuffer:
    def test_buffer_size_calculation(self, tmp_path: Path):
        buf_dir = tmp_path / "cache_scenes"
        buf_dir.mkdir()
        (buf_dir / "f1.bin").write_bytes(b"A" * 1024 * 1024)  # 1 MB
        (buf_dir / "sub").mkdir()
        (buf_dir / "sub" / "f2.bin").write_bytes(b"B" * 2 * 1024 * 1024)  # 2 MB

        rdb = RollingDiskBuffer(max_buffer_gb=0.01, buffer_dir=buf_dir)
        size_bytes = rdb.get_buffer_size_bytes()
        assert size_bytes == 3 * 1024 * 1024
        assert rdb.measure_directory_bytes() == 3 * 1024 * 1024
        assert rdb.measure_directory_bytes(buf_dir) == 3 * 1024 * 1024
        assert pytest.approx(rdb.get_buffer_size_gb(), rel=1e-3) == (3 / 1024)

    def test_buffer_safety_check(self, tmp_path: Path):
        buf_dir = tmp_path / "cache_scenes"
        buf_dir.mkdir()
        # Set max limit to 10 MB = ~0.009765 GB
        max_gb = 10 / 1024
        rdb = RollingDiskBuffer(max_buffer_gb=max_gb, buffer_dir=buf_dir)

        (buf_dir / "file1.bin").write_bytes(b"X" * 5 * 1024 * 1024)  # 5 MB
        assert rdb.is_buffer_safe() is True

        (buf_dir / "file2.bin").write_bytes(b"Y" * 6 * 1024 * 1024)  # +6 MB = 11 MB > 10 MB
        assert rdb.is_buffer_safe() is False

    def test_cleanup_files(self, tmp_path: Path):
        buf_dir = tmp_path / "cache_scenes"
        buf_dir.mkdir()
        f1 = buf_dir / "scene_001.mp4"
        f2 = buf_dir / "scene_002.mp4"
        f1.write_bytes(b"12345")
        f2.write_bytes(b"67890")

        rdb = RollingDiskBuffer(max_buffer_gb=5.0, buffer_dir=buf_dir)
        deleted = rdb.cleanup_files([f1, f2, buf_dir / "nonexistent.mp4"])
        assert deleted == 2
        assert not f1.exists()
        assert not f2.exists()

        metrics = rdb.get_metrics()
        assert metrics["total_files_deleted"] == 2
        assert metrics["total_freed_bytes"] == 10

    def test_cleanup_chapter_scenes(self, tmp_path: Path):
        buf_dir = tmp_path / "cache_scenes"
        buf_dir.mkdir()
        scenes = [buf_dir / f"scene_{i:03d}.mp4" for i in range(5)]
        for s in scenes:
            s.write_bytes(b"dummy")

        rdb = RollingDiskBuffer(max_buffer_gb=5.0, buffer_dir=buf_dir)
        deleted = rdb.cleanup_chapter_scenes("proj_test", scenes)
        assert deleted == 5
        assert all(not s.exists() for s in scenes)

    def test_enforce_buffer_limit_purging(self, tmp_path: Path):
        buf_dir = tmp_path / "cache_scenes"
        buf_dir.mkdir()
        # Max limit 5 KB
        max_gb = 5 / (1024 * 1024)
        rdb = RollingDiskBuffer(max_buffer_gb=max_gb, buffer_dir=buf_dir)

        f1 = buf_dir / "old_1.bin"
        f2 = buf_dir / "old_2.bin"
        f3 = buf_dir / "new_protected.bin"

        f1.write_bytes(b"A" * 3000)
        time.sleep(0.01)
        f2.write_bytes(b"B" * 3000)
        time.sleep(0.01)
        f3.write_bytes(b"C" * 3000)

        # Total is 9000 bytes > 5120 bytes
        assert rdb.is_buffer_safe() is False

        # Protect f3, oldest should be purged first
        purged = rdb.enforce_buffer_limit(protected_paths={f3})
        assert purged >= 1
        assert f3.exists()  # Protected file preserved
        assert not f1.exists()  # Oldest purged


# --- 2. Tests for ConcatDemuxer ---

class TestConcatDemuxer:
    def test_manifest_generation(self, tmp_path: Path):
        f1 = tmp_path / "part_01.mp4"
        f2 = tmp_path / "part_02.mp4"
        f1.write_text("dummy1")
        f2.write_text("dummy2")

        demuxer = ConcatDemuxer()
        manifest_path = demuxer.generate_concat_manifest([f1, f2])

        assert manifest_path.exists()
        content = manifest_path.read_text(encoding="utf-8")
        assert f"file '{f1.resolve().as_posix()}'\n" in content
        assert f"file '{f2.resolve().as_posix()}'\n" in content

        # Cleanup
        manifest_path.unlink()

    def test_manifest_escaping_single_quotes(self, tmp_path: Path):
        special_dir = tmp_path / "user's video"
        special_dir.mkdir()
        f1 = special_dir / "clip'1.mp4"
        f1.write_text("data")

        demuxer = ConcatDemuxer()
        manifest_path = demuxer.generate_concat_manifest([f1])
        content = manifest_path.read_text(encoding="utf-8")
        # Single quote should be escaped as '\''
        assert "'\\''" in content
        manifest_path.unlink()

    def test_manifest_validation_empty_and_missing(self, tmp_path: Path):
        demuxer = ConcatDemuxer()
        with pytest.raises(ValueError, match="cannot be empty"):
            demuxer.generate_concat_manifest([])

        with pytest.raises(FileNotFoundError):
            demuxer.generate_concat_manifest([tmp_path / "nonexistent.mp4"])

        empty_file = tmp_path / "empty.mp4"
        empty_file.touch()
        with pytest.raises(ValueError, match="is empty"):
            demuxer.generate_concat_manifest([empty_file])

    def test_concat_validation(self, tmp_path: Path):
        demuxer = ConcatDemuxer()
        with pytest.raises(ValueError, match="cannot be empty"):
            demuxer.concat([], tmp_path / "out.mp4")

    def test_concat_execution_mocked_ffmpeg_failure(self, tmp_path: Path):
        f1 = tmp_path / "p1.mp4"
        f1.write_bytes(b"abc")
        mock_bm = MagicMock()
        mock_bm.require.return_value.path = Path("ffmpeg")
        demuxer = ConcatDemuxer(binary_manager=mock_bm)

        mock_proc = MagicMock(returncode=1, stderr="Invalid stream format", stdout="")
        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(ConcatDemuxerError, match="Invalid stream format"):
                demuxer.concat([f1], tmp_path / "out.mp4")

    def test_concat_intermediate_parts_cleanup(self, tmp_path: Path):
        f1 = tmp_path / "p1.mp4"
        f2 = tmp_path / "p2.mp4"
        out = tmp_path / "final.mp4"
        f1.write_bytes(b"part1")
        f2.write_bytes(b"part2")
        out.write_bytes(b"final_data")

        mock_bm = MagicMock()
        mock_bm.require.return_value.path = Path("ffmpeg")
        demuxer = ConcatDemuxer(binary_manager=mock_bm)

        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        mock_probe = VideoProbeInfo(
            file_path=out,
            width=1920,
            height=1080,
            duration_sec=10.0,
            fps=30.0,
            has_audio=True,
            codec_name="h264",
            aspect_ratio=1.7778,
            is_vertical=False,
        )

        with patch("subprocess.run", return_value=mock_proc), patch(
            "autovideo.production.concat_demuxer.probe_video", return_value=mock_probe
        ):
            res = demuxer.concat([f1, f2], out, clean_intermediate_parts=True)
            assert res.intermediate_cleaned is True
            assert not f1.exists()
            assert not f2.exists()
            assert out.exists()


# --- 3. Tests for PipelineCheckpoint ---

class TestPipelineCheckpoint:
    def test_checkpoint_save_and_load(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        ckpt = PipelineCheckpoint(
            project_id="proj_01",
            status="in_progress",
            completed_chapters=[1, 2],
            chapter_parts={"1": "parts/part_01.mp4", "2": "parts/part_02.mp4"},
        )
        ckpt.save(state_file)
        assert state_file.exists()

        loaded = PipelineCheckpoint.load(state_file)
        assert loaded is not None
        assert loaded.project_id == "proj_01"
        assert loaded.status == "in_progress"
        assert loaded.completed_chapters == [1, 2]
        assert loaded.chapter_parts["1"] == "parts/part_01.mp4"

    def test_checkpoint_load_nonexistent_or_corrupt(self, tmp_path: Path):
        assert PipelineCheckpoint.load(tmp_path / "none.json") is None

        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("invalid json content")
        assert PipelineCheckpoint.load(corrupt) is None


# --- 4. Tests for ChapterBuilder Unit Logic ---

class TestChapterBuilder:
    def test_is_chapter_part_valid(self, tmp_path: Path):
        builder = ChapterBuilder()
        assert builder.is_chapter_part_valid(tmp_path / "missing.mp4") is False

        empty_file = tmp_path / "empty.mp4"
        empty_file.touch()
        assert builder.is_chapter_part_valid(empty_file) is False

    def test_build_chapter_resume_skip(self, tmp_path: Path):
        config = AppConfig.from_base_dir(tmp_path)
        builder = ChapterBuilder(config=config)

        parts_dir = tmp_path / "renders" / "test_p" / "parts"
        parts_dir.mkdir(parents=True)
        part1 = parts_dir / "part_01.mp4"
        part1.write_bytes(b"dummy")

        mock_probe = VideoProbeInfo(
            file_path=part1,
            width=1920,
            height=1080,
            duration_sec=5.0,
            fps=30.0,
            has_audio=True,
            codec_name="h264",
            aspect_ratio=1.7778,
            is_vertical=False,
        )

        with patch.object(builder, "is_chapter_part_valid", return_value=True), patch(
            "autovideo.production.chapter_builder.probe_video", return_value=mock_probe
        ):
            chapter = Chapter(
                chapter_index=1,
                title="Chapter One",
                scenes=[
                    Scene(
                        scene_id="S1",
                        text="Test scene",
                        duration_sec=5.0,
                        word_count=10,
                        visual_prompt="shot",
                    )
                ],
            )
            res = builder.build_chapter(
                project_id="test_p",
                chapter=chapter,
                asset_resolver={},
                parts_dir=parts_dir,
                resume=True,
            )
            assert res.skipped_from_cache is True
            assert res.part_path == part1
            assert res.duration_sec == 5.0

    def test_missing_assets_in_resolver_dict_raises(self, tmp_path: Path):
        config = AppConfig.from_base_dir(tmp_path)
        builder = ChapterBuilder(config=config)

        chapter = Chapter(
            chapter_index=1,
            title="Chapter One",
            scenes=[
                Scene(
                    scene_id="MISSING_SCENE",
                    text="Hello",
                    duration_sec=5.0,
                    word_count=10,
                    visual_prompt="shot",
                )
            ],
        )

        with pytest.raises(ChapterBuilderError, match="Missing assets"):
            builder.build_chapter(
                project_id="proj_err",
                chapter=chapter,
                asset_resolver={},  # Empty dict lacks MISSING_SCENE
                resume=False,
            )


# --- 5. Full Real Integration Tests (End-to-End B3 with FFmpeg) ---

class TestProductionPipelineIntegration:
    @pytest.fixture
    def test_assets(self, tmp_path: Path):
        """Creates real synthetic test video and audio files."""
        media_clip = tmp_path / "raw" / "vertical_clip.mp4"
        create_test_mp4(media_clip, width=720, height=1280, duration_sec=1.2)

        audio_s1 = tmp_path / "audio" / "audio_s1.wav"
        audio_s2 = tmp_path / "audio" / "audio_s2.wav"
        create_test_wav(audio_s1, duration_sec=1.0)
        create_test_wav(audio_s2, duration_sec=1.0)

        return {
            "media": media_clip,
            "audio1": audio_s1,
            "audio2": audio_s2,
        }

    def test_full_chapter_pipeline_and_concat(self, tmp_path: Path, test_assets):
        """
        Renders 2 Chapters (2 scenes in Ch1, 1 scene in Ch2),
        verifies rolling buffer cleanup of atomic scenes,
        verifies Concat Demuxer produces valid final_video.mp4,
        and verifies fault-tolerant --resume behavior.
        """
        app_config = AppConfig.from_base_dir(tmp_path)
        project_id = "test_e2e_proj"

        screenplay = Screenplay(
            title="Test Documentary",
            topic="B3 Architecture",
            skill_id="military",
            chapters=[
                Chapter(
                    chapter_index=1,
                    title="Introduction",
                    scenes=[
                        Scene(
                            scene_id="SCENE_01",
                            chapter_index=1,
                            text="Câu mở đầu bí ẩn.",
                            duration_sec=1.0,
                            word_count=5,
                            visual_prompt="wide shot",
                        ),
                        Scene(
                            scene_id="SCENE_02",
                            chapter_index=1,
                            text="Phân tích tình huống.",
                            duration_sec=1.0,
                            word_count=5,
                            visual_prompt="close shot",
                        ),
                    ],
                ),
                Chapter(
                    chapter_index=2,
                    title="Climax",
                    scenes=[
                        Scene(
                            scene_id="SCENE_03",
                            chapter_index=2,
                            text="Kết luận quan trọng.",
                            duration_sec=1.0,
                            word_count=5,
                            visual_prompt="dramatic shot",
                        ),
                    ],
                ),
            ],
        )

        asset_map = {
            "SCENE_01": SceneAssets(media_path=test_assets["media"], audio_path=test_assets["audio1"]),
            "SCENE_02": SceneAssets(media_path=test_assets["media"], audio_path=test_assets["audio2"]),
            "SCENE_03": SceneAssets(media_path=test_assets["media"], audio_path=test_assets["audio1"]),
        }

        pipeline = ProductionPipeline(config=app_config)

        # 1. First run: Renders both chapters from scratch
        result = pipeline.run(
            project_id=project_id,
            screenplay=screenplay,
            asset_resolver=asset_map,
            resume=True,
            clean_intermediate_parts=False,
        )

        assert result.project_id == project_id
        assert result.final_video_path.exists()
        assert len(result.chapter_results) == 2
        assert result.resumed_chapters_count == 0

        # Concat duration check (super fast: should be well under 10 seconds for test clips)
        assert result.concat_elapsed_sec < 10.0

        # Check atomic scenes cleanup by Rolling Buffer
        temp_scenes_dir = app_config.paths.cache_temp_scenes_dir / project_id
        remaining_temp_scenes = list(temp_scenes_dir.glob("*.mp4"))
        assert len(remaining_temp_scenes) == 0, "Rolling buffer failed to clean intermediate scene MP4s"
        assert result.buffer_metrics["total_files_deleted"] == 3

        # Probe final video output
        probe = probe_video(result.final_video_path)
        assert probe.width == 1920
        assert probe.height == 1080
        assert probe.fps in [30.0, 240.0] or (probe.total_frames and round(probe.total_frames / probe.duration_sec) == 30)
        assert probe.has_audio is True
        # Total duration should be approx 3 seconds (1s + 1s + 1s)
        assert 2.5 <= probe.duration_sec <= 4.0

        # Verify state checkpoint
        state_file = app_config.paths.get_project_render_dir(project_id) / "state.json"
        assert state_file.exists()
        ckpt = PipelineCheckpoint.load(state_file)
        assert ckpt is not None
        assert ckpt.status == "completed"
        assert ckpt.completed_chapters == [1, 2]

        # 2. Second run with resume=True: Both chapters should be skipped from cache!
        second_result = pipeline.run(
            project_id=project_id,
            screenplay=screenplay,
            asset_resolver=asset_map,
            resume=True,
        )

        assert second_result.resumed_chapters_count == 2
        assert all(cr.skipped_from_cache for cr in second_result.chapter_results)
