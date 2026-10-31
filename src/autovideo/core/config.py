"""
Configuration manager for BanContentAuto.
Manages file structure paths, concurrency limits (NFR-PERF-01),
output compliance standards (NFR-COMP-01), jitter delays, and script word budgets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _detect_default_base_dir() -> Path:
    """Detect the root project directory by traversing upward from this file."""
    current = Path(__file__).resolve()
    # Path is .../src/autovideo/core/config.py -> parent(3) is project root
    for parent in current.parents:
        if (parent / "project").exists() or (parent / "src").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


@dataclass
class PathConfig:
    """Directory paths for the project structure."""

    base_dir: Path = field(default_factory=_detect_default_base_dir)

    @property
    def bin_dir(self) -> Path:
        return self.base_dir / "bin"

    @property
    def config_dir(self) -> Path:
        return self.base_dir / "config"

    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "cache"

    @property
    def cache_audio_dir(self) -> Path:
        return self.cache_dir / "audio"

    @property
    def cache_raw_assets_dir(self) -> Path:
        return self.cache_dir / "raw_assets"

    @property
    def cache_raw_footage_dir(self) -> Path:
        return self.cache_dir / "raw_footage"

    @property
    def cache_temp_scenes_dir(self) -> Path:
        return self.cache_dir / "temp_scenes"

    @property
    def renders_dir(self) -> Path:
        return self.base_dir / "renders"

    def get_project_render_dir(self, project_id: str) -> Path:
        """Returns the output directory for a specific project."""
        return self.renders_dir / project_id

    def ensure_directories(self) -> None:
        """Creates required runtime directories if they do not already exist."""
        directories = [
            self.bin_dir,
            self.config_dir,
            self.cache_dir,
            self.cache_audio_dir,
            self.cache_raw_assets_dir,
            self.cache_raw_footage_dir,
            self.cache_temp_scenes_dir,
            self.renders_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class PerformanceConfig:
    """Performance and concurrency limits (NFR-PERF-01)."""

    render_concurrency: int = 2
    download_concurrency: int = 4
    rolling_buffer_max_gb: float = 5.0
    clean_intermediate_parts: bool = True


@dataclass
class ComplianceConfig:
    """Output video and audio standard compliance settings (NFR-COMP-01)."""

    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30
    video_codec: str = "libx264"
    video_preset: str = "veryfast"
    video_profile: str = "high"
    video_level: str = "4.1"
    video_pix_fmt: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48000
    target_lufs: float = -14.0


@dataclass
class SourcingConfig:
    """Asset sourcing jitter, anti-rate-limit, and timeout configurations."""

    jitter_min_sec: float = 2.0
    jitter_max_sec: float = 5.0
    request_timeout_sec: int = 30
    max_retries: int = 3


@dataclass
class ScriptBudgetConfig:
    """Scriptwriting word budget and rhythm standards."""

    min_words_per_sec: float = 2.5
    max_words_per_sec: float = 3.2
    min_scene_sec: float = 4.0
    max_scene_sec: float = 8.0
    min_cv: float = 0.4  # Coefficient of variation for sentence length rhythm


@dataclass
class PublishingConfig:
    """Publishing, counterpoint thumbnail, and SEO packaging configuration (B4)."""

    thumbnail_width: int = 1920
    thumbnail_height: int = 1080
    safe_zone_width_ratio: float = 0.20  # 20% width from right edge (80%-100%)
    safe_zone_height_ratio: float = 0.25  # 25% height from bottom edge (75%-100%)
    youtube_mock_mode: bool = True
    default_theme: str = "dark_dramatic"


@dataclass
class AppConfig:
    """Master application configuration aggregate."""

    paths: PathConfig = field(default_factory=PathConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    compliance: ComplianceConfig = field(default_factory=ComplianceConfig)
    sourcing: SourcingConfig = field(default_factory=SourcingConfig)
    script_budget: ScriptBudgetConfig = field(default_factory=ScriptBudgetConfig)
    publishing: PublishingConfig = field(default_factory=PublishingConfig)

    @classmethod
    def from_base_dir(cls, base_dir: Path | str) -> AppConfig:
        """Construct AppConfig with a specified base directory."""
        return cls(paths=PathConfig(base_dir=Path(base_dir).resolve()))

    def ensure_directories(self) -> None:
        """Delegate ensure_directories call to path configuration."""
        self.paths.ensure_directories()


_global_config: Optional[AppConfig] = None


def get_config(reload: bool = False, base_dir: Optional[Path | str] = None) -> AppConfig:
    """
    Get the global AppConfig singleton instance.
    Optionally reload or provide an explicit base directory.
    """
    global _global_config
    if _global_config is None or reload or base_dir is not None:
        if base_dir is not None:
            _global_config = AppConfig.from_base_dir(base_dir)
        else:
            _global_config = AppConfig()
    return _global_config
