"""
Edge-TTS Adapter (Microsoft Neural Online Voiceover).
Provides fast, high-quality Vietnamese narration (vi-VN-NamMinhNeural, vi-VN-HoaiMyNeural).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from autovideo.voiceover.timing_probe import TimingProbe
from autovideo.voiceover.zerotts_adapter import SynthesisResult

logger = logging.getLogger(__name__)


@dataclass
class EdgeTTSConfig:
    voice_id: str = "vi-VN-NamMinhNeural"
    speed: float = 1.0


class EdgeTTSAdapter:
    """Adapter for Microsoft Edge Neural TTS."""

    def __init__(
        self,
        config: Optional[EdgeTTSConfig] = None,
        timing_probe: Optional[TimingProbe] = None,
    ):
        self.config = config or EdgeTTSConfig()
        self._timing_probe = timing_probe or TimingProbe()

    def synthesize(
        self,
        text: str,
        output_path: Path | str,
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SynthesisResult:
        import edge_tts

        dest = Path(output_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        selected_voice = voice_id or self.config.voice_id
        selected_speed = speed if speed is not None else self.config.speed

        rate_str = "+0%"
        if selected_speed and selected_speed != 1.0:
            diff = int((selected_speed - 1.0) * 100)
            rate_str = f"{'+' if diff >= 0 else ''}{diff}%"

        async def _run() -> None:
            last_err = None
            for attempt in range(3):
                try:
                    comm = edge_tts.Communicate(text, selected_voice, rate=rate_str)
                    await comm.save(str(dest))
                    return
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.8 * (attempt + 1))
            if last_err:
                raise last_err

        try:
            asyncio.run(_run())
        except Exception as exc:
            logger.warning("EdgeTTS failed (%s), falling back to gTTS: %s", exc, text[:30])
            try:
                from gtts import gTTS
                g_tts = gTTS(text, lang="vi")
                g_tts.save(str(dest))
            except Exception as g_exc:
                raise RuntimeError(f"Both EdgeTTS and gTTS failed: {g_exc}") from exc

        probe = self._timing_probe.probe(dest)

        return SynthesisResult(
            audio_path=dest,
            duration_sec=probe.duration_sec,
            duration_ms=probe.duration_ms,
            text=text,
            voice_id=selected_voice,
            sample_rate=probe.sample_rate or 24000,
            engine="edge_tts",
        )
