"""
Unit and Integration Tests for Voiceover & Audio Timing Engine (WU-04, REQ-B2-03, NFR-COST-01).
Verifies:
1. Precision Timing Probe accuracy (<= 10ms error tolerance).
2. ZeroTTS offline adapter, punctuation-based breathing cadence, deterministic synthesis.
3. MaziaoTTS fallback adapter, payload formatting, retry behavior, error handling.
4. VoiceoverManager orchestration, screenplay duration synchronization, and caching.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from autovideo.core.config import AppConfig
from autovideo.script.pipeline import Chapter, Scene, SceneKeyword, Screenplay
from autovideo.voiceover.edge_adapter import EdgeTTSAdapter
from autovideo.voiceover.manager import VoiceoverConfig, VoiceoverManager, VoiceoverResult
from autovideo.voiceover.maziao_adapter import (
    MaziaoAPIError,
    MaziaoTimeoutError,
    MaziaoTTSAdapter,
    MaziaoTTSConfig,
)
from autovideo.voiceover.timing_probe import (
    AudioProbeError,
    AudioProbeResult,
    TimingProbe,
    probe_audio_duration,
)
from autovideo.voiceover.zerotts_adapter import (
    PRESET_VOICES,
    PUNCTUATION_PAUSES,
    SynthesisResult,
    TTSVoiceConfig,
    ZeroTTSAdapter,
)


# --- Helper: Generate Pure Sine Wave Test Audio ---

def create_test_wav(
    file_path: Path,
    duration_sec: float,
    sample_rate: int = 24000,
    frequency: float = 440.0,
) -> Path:
    """Helper creating a valid PCM 16-bit WAV file with exact sample count."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration_sec * sample_rate)

    with wave.open(str(file_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            val = int(8000.0 * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wav.writeframes(frames)
    return file_path


# --- 1. TimingProbe Tests ---

class TestTimingProbe:
    """Tests for mutagen-based precision timing probe and ffprobe fallback."""

    def test_probe_exact_wav_durations(self, tmp_path: Path):
        """Verifies TimingProbe precision error is <= 5ms (well within <= 10ms requirement)."""
        probe = TimingProbe()

        test_cases = [
            (1.000, 24000),
            (2.500, 24000),
            (0.350, 16000),
            (5.125, 44100),
        ]

        for expected_sec, sr in test_cases:
            wav_file = tmp_path / f"test_{int(expected_sec * 1000)}ms.wav"
            create_test_wav(wav_file, expected_sec, sample_rate=sr)

            result = probe.probe(wav_file)

            # Error must be <= 0.005s (5ms)
            error_sec = abs(result.duration_sec - expected_sec)
            assert error_sec <= 0.005, f"Expected {expected_sec}s, got {result.duration_sec}s (error: {error_sec}s)"
            assert result.sample_rate == sr
            assert result.channels == 1
            assert result.format == "wav"
            assert result.probe_method == "mutagen"
            assert abs(result.duration_ms - int(expected_sec * 1000)) <= 5

    def test_probe_audio_duration_helper(self, tmp_path: Path):
        """Tests probe_audio_duration convenience function."""
        wav_file = tmp_path / "helper.wav"
        create_test_wav(wav_file, 1.750, sample_rate=24000)

        duration = probe_audio_duration(wav_file)
        assert abs(duration - 1.750) <= 0.005

    def test_probe_missing_file_raises_error(self, tmp_path: Path):
        """Tests FileNotFoundError when probing non-existent file."""
        probe = TimingProbe()
        with pytest.raises(FileNotFoundError):
            probe.probe(tmp_path / "does_not_exist.wav")

    def test_probe_empty_file_raises_error(self, tmp_path: Path):
        """Tests ValueError when file exists but is 0 bytes."""
        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")

        probe = TimingProbe()
        with pytest.raises(ValueError, match="0 bytes"):
            probe.probe(empty_file)

    def test_ffprobe_fallback_when_mutagen_fails(self, tmp_path: Path):
        """Tests seamless fallback to ffprobe when mutagen cannot probe the file."""
        wav_file = tmp_path / "fallback.wav"
        create_test_wav(wav_file, 1.200, sample_rate=24000)

        probe = TimingProbe()

        # Mock mutagen to return None (simulating unsupported format or header failure)
        with patch.object(probe, "_probe_with_mutagen", return_value=None):
            with patch.object(
                probe,
                "_probe_with_ffprobe",
                return_value=AudioProbeResult(
                    file_path=wav_file,
                    duration_sec=1.200,
                    duration_ms=1200,
                    sample_rate=24000,
                    channels=1,
                    format="wav",
                    probe_method="ffprobe",
                ),
            ) as mock_ffprobe:
                result = probe.probe(wav_file)
                mock_ffprobe.assert_called_once()
                assert result.probe_method == "ffprobe"
                assert result.duration_sec == 1.200

    def test_probe_error_when_both_methods_fail(self, tmp_path: Path):
        """Tests AudioProbeError when both mutagen and ffprobe fail."""
        corrupt_file = tmp_path / "corrupt.audio"
        corrupt_file.write_bytes(b"corrupt content not audio")

        probe = TimingProbe()
        with patch.object(probe, "_probe_with_mutagen", return_value=None):
            with patch.object(probe, "_probe_with_ffprobe", return_value=None):
                with pytest.raises(AudioProbeError):
                    probe.probe(corrupt_file)


# --- 2. ZeroTTSAdapter Tests ---

class TestZeroTTSAdapter:
    """Tests for ZeroTTS offline engine and cadence preprocessor."""

    def test_punctuation_pause_values(self):
        """Verifies configured punctuation pause values."""
        assert PUNCTUATION_PAUSES["."] == 0.50
        assert PUNCTUATION_PAUSES[","] == 0.20
        assert PUNCTUATION_PAUSES["—"] == 0.30
        assert PUNCTUATION_PAUSES["..."] == 0.70
        assert PUNCTUATION_PAUSES["!"] == 0.40
        assert PUNCTUATION_PAUSES["?"] == 0.40

    def test_preprocess_speech_segments(self):
        """Verifies text is split into phrases with proper pause assignments."""
        text = "Đây là cú sốc. Liệu bạn có tin, điều đó là thật... Tuyệt vời!"
        segments = ZeroTTSAdapter.preprocess_speech_segments(text)

        assert len(segments) >= 4
        # Verify first segment ends with . and has 0.5s pause
        assert segments[0].punctuation == "."
        assert segments[0].pause_sec == 0.50

        # Verify second segment ends with , and has 0.2s pause
        assert segments[1].punctuation == ","
        assert segments[1].pause_sec == 0.20

        # Verify third segment ends with ... and has 0.7s pause
        assert segments[2].punctuation == "..."
        assert segments[2].pause_sec == 0.70

        # Verify fourth segment ends with ! and has 0.4s pause
        assert segments[3].punctuation == "!"
        assert segments[3].pause_sec == 0.40

    def test_preprocess_speech_segments_em_dash(self):
        """Verifies em-dash pause processing."""
        text = "Nhìn bề ngoài rất bình thường — nhưng bên trong đã rỗng tuếch."
        segments = ZeroTTSAdapter.preprocess_speech_segments(text)
        assert any(seg.punctuation == "—" and seg.pause_sec == 0.30 for seg in segments)

    def test_preprocess_empty_text(self):
        """Verifies empty or whitespace text returns empty list."""
        assert ZeroTTSAdapter.preprocess_speech_segments("") == []
        assert ZeroTTSAdapter.preprocess_speech_segments("   ") == []

    def test_calculate_estimated_duration(self):
        """Verifies duration scales with speech rate."""
        text = "Đây là bản tin tài chính đặc biệt buổi tối hôm nay."
        normal_dur = ZeroTTSAdapter.calculate_estimated_duration(text, speed=1.0)
        fast_dur = ZeroTTSAdapter.calculate_estimated_duration(text, speed=1.5)
        slow_dur = ZeroTTSAdapter.calculate_estimated_duration(text, speed=0.75)

        assert fast_dur < normal_dur < slow_dur

    def test_synthesize_generates_valid_audio(self, tmp_path: Path):
        """Tests ZeroTTS synthesis generates a playable WAV file measurable by TimingProbe."""
        adapter = ZeroTTSAdapter(config=TTSVoiceConfig(voice_id="banmai"))
        out_file = tmp_path / "voice_banmai.wav"

        result = adapter.synthesize(
            text="Một chiếc container 40 feet bất ngờ lật nghiêng giữa ngã tư.",
            output_path=out_file,
            voice_id="banmai",
        )

        assert result.audio_path.exists()
        assert result.audio_path.stat().st_size > 0
        assert result.voice_id == "banmai"
        assert result.duration_sec > 1.0
        assert result.duration_ms == int(round(result.duration_sec * 1000))
        assert result.sample_rate in (24000, 48000)

        # Verify external probe validates the file
        probe = TimingProbe()
        probed = probe.probe(out_file)
        assert abs(probed.duration_sec - result.duration_sec) <= 0.005

    def test_synthesize_preset_voices(self, tmp_path: Path):
        """Verifies all preset voices are recognized."""
        adapter = ZeroTTSAdapter()
        for voice_id in PRESET_VOICES.keys():
            out_file = tmp_path / f"voice_{voice_id}.wav"
            res = adapter.synthesize("Kiểm tra giọng nói.", out_file, voice_id=voice_id)
            assert res.voice_id == voice_id
            assert out_file.exists()


# --- 3. MaziaoTTSAdapter Tests ---

class TestMaziaoTTSAdapter:
    """Tests for Maziao cloud fallback TTS adapter."""

    def test_build_submit_payload_paragraph(self):
        """Tests request payload structure in paragraph mode."""
        adapter = MaziaoTTSAdapter()
        payload = adapter.build_submit_payload(
            text="Xin chào các bạn",
            mode="paragraph",
            voice_id="zv_vi_sg_male_thien_tam",
            speed=1.1,
        )

        assert payload["mode"] == "paragraph"
        assert payload["parts"][0]["text"] == "Xin chào các bạn"
        assert payload["voiceId"] == "zv_vi_sg_male_thien_tam"
        assert payload["config"]["speed"] == 1.1
        assert payload["modelId"] == "lingual_speech_v2"

    def test_build_submit_payload_subtitle(self):
        """Tests request payload structure in subtitle mode with timestamps."""
        adapter = MaziaoTTSAdapter()
        payload = adapter.build_submit_payload(
            text="Đoạn thoại có timing",
            mode="subtitle",
            start_time=1.5,
            end_time=5.5,
        )

        assert payload["mode"] == "subtitle"
        assert payload["parts"][0]["startTime"] == 1.5
        assert payload["parts"][0]["endTime"] == 5.5

    def test_mock_mode_synthesis(self, tmp_path: Path):
        """Tests mock mode completes submission, polling, and produces valid audio."""
        config = MaziaoTTSConfig(mock_mode=True)
        adapter = MaziaoTTSAdapter(config=config)
        out_file = tmp_path / "maziao_mock.wav"

        result = adapter.synthesize(
            text="Kiểm tra Maziao TTS fallback trong chế độ mock.",
            output_path=out_file,
        )

        assert result.audio_path.exists()
        assert result.audio_path.stat().st_size > 0
        assert result.engine == "maziao"
        assert result.duration_sec > 0.5

    def test_api_submit_and_poll_flow(self, tmp_path: Path):
        """Tests HTTP workflow with mocked responses."""
        session = MagicMock(spec=requests.Session)

        # Mock submit response
        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"data": {"taskId": "task_123"}}

        # Mock status response (completed)
        status_resp = MagicMock()
        status_resp.status_code = 200
        status_resp.json.return_value = {
            "data": [{"id": "task_123", "status": "completed", "resultUrl": "https://r2.maziao.com/audio.wav"}]
        }

        # Mock download response
        download_resp = MagicMock()
        download_resp.status_code = 200

        # Generate actual small WAV bytes for download
        dummy_wav = tmp_path / "dummy.wav"
        create_test_wav(dummy_wav, 1.0)
        wav_bytes = dummy_wav.read_bytes()
        download_resp.iter_content.return_value = [wav_bytes]

        session.request.side_effect = [submit_resp, status_resp]
        session.get.return_value = download_resp

        config = MaziaoTTSConfig(api_key="test_api_key", mock_mode=False)
        adapter = MaziaoTTSAdapter(config=config, session=session)

        out_file = tmp_path / "maziao_flow.wav"
        result = adapter.synthesize("Thử nghiệm submit qua API", out_file)

        assert result.engine == "maziao"
        assert abs(result.duration_sec - 1.0) <= 0.01

    def test_api_error_on_client_failure(self):
        """Tests MaziaoAPIError is raised immediately on 401 Unauthorized."""
        session = MagicMock(spec=requests.Session)
        fail_resp = MagicMock()
        fail_resp.status_code = 401
        fail_resp.text = "Unauthorized"
        session.request.return_value = fail_resp

        config = MaziaoTTSConfig(api_key="bad_key", mock_mode=False)
        adapter = MaziaoTTSAdapter(config=config, session=session)

        with pytest.raises(MaziaoAPIError) as exc_info:
            adapter.submit_task("Text")
        assert exc_info.value.status_code == 401

    def test_poll_timeout_raises_maziao_timeout_error(self):
        """Tests MaziaoTimeoutError when task remains processing past max retries."""
        session = MagicMock(spec=requests.Session)
        processing_resp = MagicMock()
        processing_resp.status_code = 200
        processing_resp.json.return_value = {"data": [{"id": "t1", "status": "processing"}]}
        session.request.return_value = processing_resp

        config = MaziaoTTSConfig(
            api_key="valid_key",
            mock_mode=False,
            max_poll_retries=2,
            poll_interval_sec=0.01,
        )
        adapter = MaziaoTTSAdapter(config=config, session=session)

        with pytest.raises(MaziaoTimeoutError):
            adapter.poll_until_complete("t1")


# --- 4. VoiceoverManager Tests ---

class TestVoiceoverManager:
    """Tests for VoiceoverManager orchestration and Screenplay timing updates."""

    @pytest.fixture
    def sample_screenplay(self) -> Screenplay:
        """Fixture returning a 2-chapter, 3-scene Screenplay."""
        s1 = Scene(
            scene_id="SCENE_001",
            chapter_index=1,
            text="Chiếc xe tải hạng nặng mất lái và lao thẳng vào dải phân cách.",
            duration_sec=5.0,  # Estimated initial duration
            word_count=13,
            visual_prompt="Truck swerving across highway lane",
            keywords=SceneKeyword(vi=["xe tải", "tai nạn"], en=["truck", "crash"], zh=["货车", "车祸"]),
        )
        s2 = Scene(
            scene_id="SCENE_002",
            chapter_index=1,
            text="Khói đen bốc lên ngùn ngụt, che khuất tầm nhìn của các tài xế phía sau.",
            duration_sec=6.0,
            word_count=16,
            visual_prompt="Dense black smoke billowing from vehicle",
            keywords=SceneKeyword(vi=["khói đen"], en=["smoke"], zh=["黑烟"]),
        )
        s3 = Scene(
            scene_id="SCENE_003",
            chapter_index=2,
            text="Lực lượng cứu hộ lập tức có mặt để phong tỏa hiện trường.",
            duration_sec=4.5,
            word_count=12,
            visual_prompt="Emergency responders setting up safety cones",
            keywords=SceneKeyword(vi=["cứu hộ"], en=["rescue"], zh=["救援"]),
        )

        return Screenplay(
            title="Sự Cố Giao Thông Khẩn Cấp",
            topic="Tai nạn xe tải",
            skill_id="traffic_analysis",
            total_duration_sec=15.5,
            total_words=41,
            chapters=[
                Chapter(chapter_index=1, title="Khoảnh Khắc Va Chạm", scenes=[s1, s2]),
                Chapter(chapter_index=2, title="Hiện Trường Ứng Cứu", scenes=[s3]),
            ],
        )

    def test_synthesize_single_scene(self, tmp_path: Path):
        """Tests synthesizing a single scene and creating output audio file."""
        app_cfg = AppConfig.from_base_dir(tmp_path)
        manager = VoiceoverManager(app_config=app_cfg)

        scene = Scene(
            scene_id="SCENE_TEST",
            chapter_index=1,
            text="Hệ thống phanh đã hoàn toàn mất tác dụng.",
            duration_sec=4.0,
            word_count=9,
            visual_prompt="Failed brakes",
        )

        result = manager.synthesize_scene(scene, scene_index=1, project_id="proj_01")
        assert result.audio_path.exists()
        assert result.duration_sec > 0.0
        assert result.engine in ("zerotts", "cached")

    def test_audio_caching_skips_resynthesis(self, tmp_path: Path):
        """Verifies that running synthesis twice on identical scene reuses cached audio."""
        app_cfg = AppConfig.from_base_dir(tmp_path)
        manager = VoiceoverManager(app_config=app_cfg)

        scene = Scene(
            scene_id="SCENE_CACHE",
            chapter_index=1,
            text="Một sự thật chấn động được phơi bày.",
            duration_sec=4.0,
            word_count=8,
            visual_prompt="Dramatic revelation",
        )

        # First run: fresh synthesis
        res1 = manager.synthesize_scene(scene, scene_index=1, project_id="proj_cache")
        assert res1.engine == "zerotts"

        # Second run: must hit cache
        res2 = manager.synthesize_scene(scene, scene_index=1, project_id="proj_cache")
        assert res2.engine == "cached"
        assert res2.audio_path == res1.audio_path
        assert res2.duration_sec == res1.duration_sec

    def test_fallback_cascade_when_zerotts_fails(self, tmp_path: Path):
        """Tests that manager falls back to Maziao when ZeroTTS fails."""
        app_cfg = AppConfig.from_base_dir(tmp_path)
        failing_zerotts = MagicMock(spec=ZeroTTSAdapter)
        failing_zerotts.synthesize.side_effect = RuntimeError("ZeroTTS CPU crash")

        failing_edge = MagicMock(spec=EdgeTTSAdapter)
        failing_edge.synthesize.side_effect = RuntimeError("EdgeTTS network error")

        # Maziao mock mode
        maziao = MaziaoTTSAdapter(config=MaziaoTTSConfig(mock_mode=True))

        manager = VoiceoverManager(
            app_config=app_cfg,
            zerotts=failing_zerotts,
            edge_tts=failing_edge,
            maziao=maziao,
            config=VoiceoverConfig(primary_engine="zerotts", enable_fallback=True),
        )

        scene = Scene(
            scene_id="SCENE_FB",
            chapter_index=1,
            text="Câu thoại cần fallback.",
            duration_sec=4.0,
            word_count=5,
            visual_prompt="Fallback visual",
        )

        result = manager.synthesize_scene(scene, scene_index=1, project_id="proj_fb")
        assert result.engine == "maziao"
        assert result.audio_path.exists()

    def test_process_screenplay_aligns_durations(self, tmp_path: Path, sample_screenplay: Screenplay):
        """
        Tests process_screenplay:
        1. Synthesizes all scenes in all chapters.
        2. Assigns exact measured audio duration to each scene.
        3. Recalculates master screenplay total duration.
        """
        app_cfg = AppConfig.from_base_dir(tmp_path)
        manager = VoiceoverManager(app_config=app_cfg)

        result = manager.process_screenplay(sample_screenplay, project_id="proj_master")

        assert len(result.audio_files) == 3
        assert len(result.durations) == 3
        assert result.total_duration_sec > 0.0

        # Verify each scene duration was updated to match probed audio duration
        probe = TimingProbe()
        for scene in sample_screenplay.all_scenes:
            audio_path = result.audio_files[scene.scene_id]
            assert audio_path.exists()
            probed = probe.probe(audio_path)
            assert abs(scene.duration_sec - probed.duration_sec) <= 0.005

        # Verify screenplay total duration matches sum of scenes
        expected_total = sum(s.duration_sec for s in sample_screenplay.all_scenes)
        assert abs(sample_screenplay.total_duration_sec - round(expected_total, 3)) <= 0.005
