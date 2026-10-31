"""
Audio-First Voiceover & Timing Engine Package (REQ-B2-03, NFR-COST-01).
Provides precision timing probe, offline ZeroTTS adapter, Maziao fallback, and VoiceoverManager.
"""

from autovideo.voiceover.manager import VoiceoverConfig, VoiceoverManager, VoiceoverResult
from autovideo.voiceover.maziao_adapter import (
    MaziaoAPIError,
    MaziaoError,
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
    SpeechSegment,
    SynthesisResult,
    TTSVoiceConfig,
    ZeroTTSAdapter,
)

__all__ = [
    "AudioProbeError",
    "AudioProbeResult",
    "MaziaoAPIError",
    "MaziaoError",
    "MaziaoTimeoutError",
    "MaziaoTTSAdapter",
    "MaziaoTTSConfig",
    "PRESET_VOICES",
    "PUNCTUATION_PAUSES",
    "SpeechSegment",
    "SynthesisResult",
    "TTSVoiceConfig",
    "TimingProbe",
    "VoiceoverConfig",
    "VoiceoverManager",
    "VoiceoverResult",
    "ZeroTTSAdapter",
    "probe_audio_duration",
]
