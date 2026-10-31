"""
Unified Voiceover Manager (REQ-B2-03, NFR-COST-01).
Orchestrates audio synthesis across all scenes in a Screenplay,
applying ZeroTTS as primary ($0 cost offline CPU) with MaziaoTTS as fallback.
Measures exact audio duration via TimingProbe, updates scene metadata, and maintains audio cache.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from autovideo.core.config import AppConfig, get_config
from autovideo.script.pipeline import Scene, Screenplay
from autovideo.voiceover.edge_adapter import EdgeTTSAdapter, EdgeTTSConfig
from autovideo.voiceover.maziao_adapter import MaziaoTTSAdapter, MaziaoTTSConfig
from autovideo.voiceover.timing_probe import TimingProbe
from autovideo.voiceover.zerotts_adapter import SynthesisResult, TTSVoiceConfig, ZeroTTSAdapter

logger = logging.getLogger(__name__)


@dataclass
class VoiceoverConfig:
    """Configuration for Voiceover Manager."""
    primary_engine: str = "zerotts"  # "zerotts" | "maziao"
    enable_fallback: bool = True
    default_voice: str = "banmai"
    speed: float = 1.0
    cache_enabled: bool = True


@dataclass
class VoiceoverResult:
    """Aggregated output from processing screenplay voiceover."""
    screenplay: Screenplay
    audio_files: Dict[str, Path] = field(default_factory=dict)
    durations: Dict[str, float] = field(default_factory=dict)
    total_duration_sec: float = 0.0
    engines_used: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_duration_sec": self.total_duration_sec,
            "scene_count": len(self.audio_files),
            "audio_files": {k: str(v) for k, v in self.audio_files.items()},
            "durations": self.durations,
            "engines_used": self.engines_used,
        }


class VoiceoverManager:
    """
    Coordinates audio-first speech synthesis and precision timing measurement.
    """

    def __init__(
        self,
        config: Optional[VoiceoverConfig] = None,
        app_config: Optional[AppConfig] = None,
        zerotts: Optional[ZeroTTSAdapter] = None,
        maziao: Optional[MaziaoTTSAdapter] = None,
        edge_tts: Optional[EdgeTTSAdapter] = None,
        timing_probe: Optional[TimingProbe] = None,
    ):
        self.config = config or VoiceoverConfig()
        self.app_config = app_config or get_config()
        self.timing_probe = timing_probe or TimingProbe()

        # Initialize engines
        self.zerotts = zerotts or ZeroTTSAdapter(
            config=TTSVoiceConfig(voice_id=self.config.default_voice, speed=self.config.speed),
            timing_probe=self.timing_probe,
        )
        self.maziao = maziao or MaziaoTTSAdapter(
            config=MaziaoTTSConfig(speed=self.config.speed),
            timing_probe=self.timing_probe,
        )
        self.edge_tts = edge_tts or EdgeTTSAdapter(
            config=EdgeTTSConfig(voice_id="vi-VN-NamMinhNeural", speed=self.config.speed),
            timing_probe=self.timing_probe,
        )

    def refresh_settings(self) -> None:
        """Dynamically reloads TTS preferences from config/settings.json."""
        try:
            from autovideo.core.settings import SettingsManager
            sm = SettingsManager(config=self.app_config)
            s = sm.load_settings()
            self.config.primary_engine = s.tts_primary_provider
            self.config.enable_fallback = s.tts_enable_fallback
            self.config.speed = s.speech_rate
            if s.tts_primary_provider == "zerotts":
                self.config.default_voice = s.zerotts_voice
            elif s.tts_primary_provider in ("edge", "edge_tts"):
                self.config.default_voice = s.edge_tts_voice
            elif s.tts_primary_provider == "maziao":
                self.config.default_voice = s.maziao_voice_id
                self.maziao.config.api_key = s.maziao_api_key
                self.maziao.config.base_url = s.maziao_base_url
                self.maziao.config.model_id = s.maziao_model_id
        except Exception as exc:
            logger.warning("Could not refresh voiceover settings: %s", exc)

    def get_audio_output_dir(self, project_id: str = "default") -> Path:
        """Returns the project's audio cache directory, creating it if needed."""
        out_dir = self.app_config.paths.cache_audio_dir / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _compute_text_hash(self, text: str, voice_id: str, speed: float) -> str:
        """Compute stable hash to verify if cached audio matches current request."""
        payload = f"{text}_{voice_id}_{speed:.2f}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:12]

    def synthesize_scene(
        self,
        scene: Scene,
        scene_index: int = 1,
        project_id: str = "default",
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SynthesisResult:
        """
        Synthesize audio for an individual scene.
        Attempts primary engine first; gracefully switches to fallback engine if enabled.
        """
        selected_voice = voice_id or self.config.default_voice
        selected_speed = speed if speed is not None else self.config.speed

        out_dir = self.get_audio_output_dir(project_id)
        text_hash = self._compute_text_hash(scene.text, selected_voice, selected_speed)
        dest_file = out_dir / f"scene_{scene_index:03d}_{text_hash}.wav"

        # Check existing cache
        if self.config.cache_enabled and dest_file.exists() and dest_file.stat().st_size > 0:
            try:
                probe = self.timing_probe.probe(dest_file)
                logger.info("Using cached audio for scene %s: %s", scene.scene_id, dest_file)
                return SynthesisResult(
                    audio_path=dest_file,
                    duration_sec=probe.duration_sec,
                    duration_ms=probe.duration_ms,
                    text=scene.text,
                    voice_id=selected_voice,
                    sample_rate=probe.sample_rate or 24000,
                    engine="cached",
                )
            except Exception:
                logger.warning("Cached audio file corrupt, regenerating: %s", dest_file)

        # 1. Primary synthesis attempt
        engine_map = {
            "zerotts": (self.zerotts, "zerotts"),
            "edge": (self.edge_tts, "edge_tts"),
            "edge_tts": (self.edge_tts, "edge_tts"),
            "maziao": (self.maziao, "maziao"),
        }

        primary_key = self.config.primary_engine if self.config.primary_engine in engine_map else "zerotts"
        primary_adapter, primary_name = engine_map[primary_key]

        # Determine cascade fallback order
        candidates = []
        if primary_key == "zerotts":
            candidates = [("edge_tts", self.edge_tts), ("maziao", self.maziao)]
        elif primary_key in ("edge", "edge_tts"):
            candidates = [("zerotts", self.zerotts), ("maziao", self.maziao)]
        else:
            candidates = [("zerotts", self.zerotts), ("edge_tts", self.edge_tts)]

        try:
            return primary_adapter.synthesize(
                text=scene.text,
                output_path=dest_file,
                voice_id=selected_voice,
                speed=selected_speed,
            )
        except Exception as exc:
            if not self.config.enable_fallback:
                raise exc
            logger.warning(
                "Primary TTS engine '%s' failed for scene %s: %s. Initiating fallback cascade.",
                primary_name,
                scene.scene_id,
                exc,
            )
            last_err = exc
            for fb_name, fb_adapter in candidates:
                try:
                    logger.info("Trying fallback TTS engine '%s' for scene %s", fb_name, scene.scene_id)
                    return fb_adapter.synthesize(
                        text=scene.text,
                        output_path=dest_file,
                        voice_id=selected_voice,
                        speed=selected_speed,
                    )
                except Exception as fb_exc:
                    logger.warning("Fallback TTS '%s' failed: %s", fb_name, fb_exc)
                    last_err = fb_exc
            raise last_err

    def process_screenplay(
        self,
        screenplay: Screenplay,
        project_id: str = "default",
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> VoiceoverResult:
        """
        Synthesize audio for all scenes in the Screenplay.
        Updates each Scene.duration_sec to match the exact measured audio duration,
        and recalculates the Screenplay.total_duration_sec.
        """
        selected_voice = voice_id or self.config.default_voice
        selected_speed = speed if speed is not None else self.config.speed

        audio_files: Dict[str, Path] = {}
        durations: Dict[str, float] = {}
        engines_used: Dict[str, str] = {}
        total_duration = 0.0

        all_scenes = screenplay.all_scenes
        for idx, scene in enumerate(all_scenes, start=1):
            result = self.synthesize_scene(
                scene=scene,
                scene_index=idx,
                project_id=project_id,
                voice_id=selected_voice,
                speed=selected_speed,
            )

            # Assign measured duration to scene (Audio-First alignment)
            scene.duration_sec = result.duration_sec
            audio_files[scene.scene_id] = result.audio_path
            durations[scene.scene_id] = result.duration_sec
            engines_used[scene.scene_id] = result.engine
            total_duration += result.duration_sec

        # Update Master Screenplay total duration
        screenplay.total_duration_sec = round(total_duration, 3)

        return VoiceoverResult(
            screenplay=screenplay,
            audio_files=audio_files,
            durations=durations,
            total_duration_sec=round(total_duration, 3),
            engines_used=engines_used,
        )
