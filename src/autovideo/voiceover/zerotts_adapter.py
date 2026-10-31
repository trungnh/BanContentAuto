"""
ZeroTTS Offline Engine Adapter (REQ-B2-03, NFR-COST-01).
Synthesizes Vietnamese speech offline on CPU ($0 external cost),
applying breath rhythm and punctuation-based pausing (., ,, —, ..., !, ?).
Supports deterministic synthesis mode for headless testing and zero-shot preset voices.
"""

from __future__ import annotations

import json
import logging
import math
import re
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from autovideo.voiceover.timing_probe import TimingProbe

logger = logging.getLogger(__name__)

# Enforce UTF-8 on Windows for zerotts voice metadata loading
try:
    import json
    from pathlib import Path
    import numpy as np
    import zerotts.voices

    _orig_load_voice_dir = zerotts.voices.load_voice_dir

    def _safe_load_voice_dir(vdir: str | Path, name: str | None = None, expect_queries: int | None = None):
        vdir = Path(vdir)
        name = name or vdir.name
        npz = vdir / "voice.npz"
        if not npz.exists():
            raise FileNotFoundError(f"{vdir} is not a voice pack: no voice.npz in it")

        data = np.load(npz)
        emb = np.asarray(data["voice_emb"], dtype=np.float32)
        if emb.ndim == 2:
            emb = emb[None, :, :]

        stored_q = int(data["n_voice_queries"]) if "n_voice_queries" in data else int(emb.shape[1])
        if stored_q != emb.shape[1]:
            raise ValueError(
                f"voice {name!r} is inconsistent: n_voice_queries={stored_q} but "
                f"voice_emb has {emb.shape[1]} queries."
            )
        if expect_queries is not None and stored_q != expect_queries:
            raise ValueError(
                f"voice {name!r} was built with n_voice_queries={stored_q}, but this "
                f"model uses {expect_queries}. It belongs to different weights."
            )

        meta_path = vdir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        preview = vdir / "preview.wav"
        return zerotts.voices.Voice(
            name=name, emb=emb, meta=meta,
            preview_path=str(preview) if preview.exists() else None
        )

    zerotts.voices.load_voice_dir = _safe_load_voice_dir
except Exception as _patch_err:
    pass

_ZEROTTS_ENGINE = None
_ZEROTTS_TRIED = False


def get_zerotts_engine():
    """Lazily loads and caches the local ZeroTTS ONNX model instance."""
    global _ZEROTTS_ENGINE, _ZEROTTS_TRIED
    if _ZEROTTS_TRIED:
        return _ZEROTTS_ENGINE
    _ZEROTTS_TRIED = True
    try:
        from zerotts import ZeroTTS
        _ZEROTTS_ENGINE = ZeroTTS.from_pretrained(local_files_only=True)
        logger.info("Successfully loaded local ZeroTTS ONNX engine.")
    except Exception as exc:
        logger.warning("Could not load local ZeroTTS from local files: %s. Trying hub fallback...", exc)
        try:
            from zerotts import ZeroTTS
            _ZEROTTS_ENGINE = ZeroTTS.from_pretrained(local_files_only=False)
            logger.info("Successfully loaded ZeroTTS from Hugging Face hub.")
        except Exception as exc2:
            logger.warning("ZeroTTS engine completely unavailable: %s. Will fallback to deterministic waveform.", exc2)
            _ZEROTTS_ENGINE = None
    return _ZEROTTS_ENGINE


@dataclass
class SpeechSegment:
    """A segment of spoken text followed by a breath/cadence pause."""
    text: str
    pause_sec: float
    punctuation: str


@dataclass
class TTSVoiceConfig:
    """Configuration for ZeroTTS synthesis."""
    voice_id: str = "banmai"
    speed: float = 1.0
    pitch: float = 1.0
    sample_rate: int = 24000
    channels: int = 1
    mock_mode: bool = False


@dataclass(frozen=True)
class SynthesisResult:
    """Synthesis output metadata."""
    audio_path: Path
    duration_sec: float
    duration_ms: int
    text: str
    voice_id: str
    sample_rate: int
    engine: str = "zerotts"

    def to_dict(self) -> dict:
        return {
            "audio_path": str(self.audio_path),
            "duration_sec": self.duration_sec,
            "duration_ms": self.duration_ms,
            "text": self.text,
            "voice_id": self.voice_id,
            "sample_rate": self.sample_rate,
            "engine": self.engine,
        }


# Vietnamese Preset Voices
PRESET_VOICES: Dict[str, Dict[str, str]] = {
    "banmai": {
        "name": "Ban Mai",
        "region": "Northern",
        "gender": "female",
        "style": "Investigative / Sharp & Crisp",
    },
    "maichi": {
        "name": "Mai Chi",
        "region": "Northern",
        "gender": "female",
        "style": "News Commentary / Balanced",
    },
    "minhquang": {
        "name": "Minh Quang",
        "region": "Northern",
        "gender": "male",
        "style": "Documentary / Deep & Resonant",
    },
    "thientam": {
        "name": "Thiện Tâm",
        "region": "Southern",
        "gender": "male",
        "style": "Storytelling / Warm Narrative",
    },
}

# Punctuation pause rules in seconds
PUNCTUATION_PAUSES: Dict[str, float] = {
    "...": 0.70,  # Deep breath / ellipsis pause
    "…": 0.70,
    ".": 0.50,   # Full stop / end of sentence
    "!": 0.40,   # Exclamation mark
    "?": 0.40,   # Question mark
    ":": 0.35,   # Colon explanation
    ";": 0.35,   # Semicolon
    "—": 0.30,   # Em-dash / tone pivot
    "--": 0.30,
    "-": 0.25,
    ",": 0.20,   # Comma / short breath
}


class ZeroTTSAdapter:
    """
    ZeroTTS speech synthesis engine adapter.
    Handles Vietnamese text preprocessing (breathing intervals and punctuation cadence),
    voice selection, and offline audio waveform generation.
    """

    def __init__(
        self,
        config: Optional[TTSVoiceConfig] = None,
        timing_probe: Optional[TimingProbe] = None,
    ):
        self.config = config or TTSVoiceConfig()
        self._timing_probe = timing_probe or TimingProbe()

    @staticmethod
    def preprocess_speech_segments(text: str) -> List[SpeechSegment]:
        """
        Parse text into speech segments and calculate pause durations based on punctuation.
        Respects:
          - '...' or '…' -> ~700ms pause
          - '.' -> ~500ms pause
          - '!' / '?' -> ~400ms pause
          - ':' / ';' -> ~350ms pause
          - '—' / '--' -> ~300ms pause
          - ',' -> ~200ms pause
        """
        cleaned = text.strip()
        if not cleaned:
            return []

        # Regex matching punctuation boundaries while preserving punctuation
        pattern = re.compile(r"(\.{3}|…|[.!?—,;:–]|-{2})")
        parts = pattern.split(cleaned)

        segments: List[SpeechSegment] = []
        i = 0
        while i < len(parts):
            phrase = parts[i].strip()
            punct = ""
            pause = 0.0

            if i + 1 < len(parts):
                punct = parts[i + 1].strip()
                pause = PUNCTUATION_PAUSES.get(punct, 0.20)
                i += 2
            else:
                i += 1

            if phrase or punct:
                segments.append(
                    SpeechSegment(
                        text=phrase,
                        pause_sec=pause,
                        punctuation=punct,
                    )
                )

        # If last segment has no terminal punctuation, provide default terminal pause
        if segments and segments[-1].pause_sec == 0.0:
            segments[-1].pause_sec = 0.40

        return segments

    @staticmethod
    def calculate_estimated_duration(
        text: str,
        speed: float = 1.0,
        words_per_sec: float = 2.85,
    ) -> float:
        """
        Estimate narration duration based on Vietnamese reading speed
        and punctuation pauses.
        """
        segments = ZeroTTSAdapter.preprocess_speech_segments(text)
        words = len(text.split())
        base_speech_sec = (words / max(0.1, words_per_sec)) / max(0.2, speed)
        pause_sec = sum(seg.pause_sec for seg in segments) / max(0.2, speed)
        return round(base_speech_sec + pause_sec, 3)

    @staticmethod
    def resolve_voice_id(voice_id: str, available_voices: List[str]) -> str:
        """Resolves user voice or legacy alias to official ZeroTTS voice."""
        if not voice_id:
            return "maichi"
        if voice_id in available_voices:
            return voice_id
        lower_v = voice_id.lower()
        for av in available_voices:
            if av.lower() == lower_v:
                return av
        aliases = {
            "banmai": "maichi",
            "minhquang": "quangminh",
            "thientam": "huuduc",
            "default": "maichi",
        }
        if lower_v in aliases and aliases[lower_v] in available_voices:
            return aliases[lower_v]
        return available_voices[0] if available_voices else "maichi"

    def synthesize(
        self,
        text: str,
        output_path: Path | str,
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SynthesisResult:
        """
        Synthesize text into an audio file.

        Args:
            text: Narration text to speak.
            output_path: Destination audio file path (.wav).
            voice_id: Preset voice identifier (e.g., 'banmai', 'maichi').
            speed: Speech rate multiplier (1.0 = normal).

        Returns:
            SynthesisResult containing audio path and measured duration.
        """
        selected_voice = voice_id or self.config.voice_id
        selected_speed = speed if speed is not None else self.config.speed
        dest = Path(output_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        synthesized_real = False
        if not self.config.mock_mode:
            engine = get_zerotts_engine()
            if engine is None:
                raise RuntimeError("Không thể tải mô hình ZeroTTS (weights chưa sẵn sàng hoặc lỗi cấu hình).")
            try:
                available = engine.list_voices()
                real_voice = self.resolve_voice_id(selected_voice, available)
                wav_data = engine.synthesize(text, voice=real_voice)
                engine.save_audio(wav_data, str(dest))
                synthesized_real = True
            except Exception as exc:
                logger.error("ZeroTTS real synthesis failed: %s", exc)
                raise RuntimeError(f"ZeroTTS tạo giọng đọc thất bại: {exc}") from exc

        if not synthesized_real:
            if self.config.mock_mode:
                self._generate_waveform(
                    text=text,
                    output_file=dest,
                    voice_id=selected_voice,
                    speed=selected_speed,
                )
            else:
                raise RuntimeError("Không thể tạo giọng đọc ZeroTTS và chế độ mock bị tắt.")

        # Probe exact duration using TimingProbe (guaranteed error <= 10ms)
        probe = self._timing_probe.probe(dest)

        return SynthesisResult(
            audio_path=dest,
            duration_sec=probe.duration_sec,
            duration_ms=probe.duration_ms,
            text=text,
            voice_id=selected_voice,
            sample_rate=probe.sample_rate or self.config.sample_rate,
            engine="zerotts",
        )

    def _generate_waveform(
        self,
        text: str,
        output_file: Path,
        voice_id: str,
        speed: float,
    ) -> None:
        """
        Generate audio waveform.
        Uses deterministic audio generation with exact PCM framing and pause spacing
        conforming to the preprocessed segments.
        """
        sample_rate = self.config.sample_rate
        channels = self.config.channels
        segments = self.preprocess_speech_segments(text)

        # Base tone frequency for voice identification in audio
        voice_frequencies: Dict[str, float] = {
            "banmai": 260.0,    # F#4 (Female higher pitch)
            "maichi": 240.0,    # B3 (Female clear pitch)
            "minhquang": 130.0,  # C3 (Male low documentary pitch)
            "thientam": 150.0,   # D3 (Male warm pitch)
        }
        base_freq = voice_frequencies.get(voice_id, 220.0)

        # Open WAV file for writing 16-bit PCM
        with wave.open(str(output_file), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)

            # Generate audio frames for each segment
            for seg in segments:
                words = len(seg.text.split())
                if words > 0:
                    # Speech duration: ~2.85 words/second modulated by speed
                    speech_duration = (words / (2.85 * max(0.2, speed)))
                    total_samples = int(speech_duration * sample_rate)

                    # Generate gently modulated acoustic wave
                    frames = bytearray()
                    for s in range(total_samples):
                        t = s / sample_rate
                        # Modulate amplitude with 4Hz syllable rhythm
                        syllable_mod = 0.5 * (1.0 + math.sin(2.0 * math.pi * 4.0 * t))
                        sample_val = int(syllable_mod * 8000.0 * math.sin(2.0 * math.pi * base_freq * t))
                        # Clamp to 16-bit signed integer
                        sample_val = max(-32767, min(32767, sample_val))
                        frames.extend(struct.pack("<h", sample_val))

                    wav.writeframes(frames)

                # Append silence pause for punctuation breath rhythm
                if seg.pause_sec > 0:
                    effective_pause = seg.pause_sec / max(0.2, speed)
                    pause_samples = int(effective_pause * sample_rate)
                    silence_frames = bytearray(struct.pack("<h", 0) * pause_samples)
                    wav.writeframes(silence_frames)
