"""
Unit tests for autovideo.core.config.
Tests path calculations, directory provisioning, and NFR compliance defaults.
"""

from pathlib import Path
import pytest

from autovideo.core.config import (
    AppConfig,
    ComplianceConfig,
    PathConfig,
    PerformanceConfig,
    ScriptBudgetConfig,
    SourcingConfig,
    get_config,
)


def test_default_config_paths():
    """Verify default paths are correctly calculated."""
    config = AppConfig()
    paths = config.paths

    assert paths.base_dir.exists()
    assert paths.bin_dir == paths.base_dir / "bin"
    assert paths.config_dir == paths.base_dir / "config"
    assert paths.cache_dir == paths.base_dir / "cache"
    assert paths.cache_audio_dir == paths.base_dir / "cache" / "audio"
    assert paths.cache_raw_assets_dir == paths.base_dir / "cache" / "raw_assets"
    assert paths.cache_temp_scenes_dir == paths.base_dir / "cache" / "temp_scenes"
    assert paths.renders_dir == paths.base_dir / "renders"


def test_custom_base_dir(tmp_path: Path):
    """Verify that specifying a custom base directory properly anchors all subpaths."""
    custom_root = tmp_path / "custom_proj"
    config = AppConfig.from_base_dir(custom_root)

    assert config.paths.base_dir == custom_root.resolve()
    assert config.paths.bin_dir == custom_root.resolve() / "bin"
    assert config.paths.cache_dir == custom_root.resolve() / "cache"
    assert config.paths.renders_dir == custom_root.resolve() / "renders"

    project_id = "test_run_001"
    proj_dir = config.paths.get_project_render_dir(project_id)
    assert proj_dir == custom_root.resolve() / "renders" / project_id


def test_ensure_directories(tmp_path: Path):
    """Verify that ensure_directories() creates all required directories on disk."""
    custom_root = tmp_path / "test_workspace"
    config = AppConfig.from_base_dir(custom_root)

    assert not config.paths.cache_dir.exists()
    assert not config.paths.renders_dir.exists()

    config.ensure_directories()

    assert config.paths.bin_dir.is_dir()
    assert config.paths.config_dir.is_dir()
    assert config.paths.cache_dir.is_dir()
    assert config.paths.cache_audio_dir.is_dir()
    assert config.paths.cache_raw_assets_dir.is_dir()
    assert config.paths.cache_temp_scenes_dir.is_dir()
    assert config.paths.renders_dir.is_dir()


def test_nfr_performance_defaults():
    """Verify performance configuration matches NFR-PERF-01."""
    perf = PerformanceConfig()
    assert perf.render_concurrency == 2
    assert perf.download_concurrency == 4
    assert perf.rolling_buffer_max_gb == 5.0
    assert perf.clean_intermediate_parts is True


def test_nfr_compliance_defaults():
    """Verify output format defaults match NFR-COMP-01 standard specifications."""
    comp = ComplianceConfig()
    assert comp.video_width == 1920
    assert comp.video_height == 1080
    assert comp.video_fps == 30
    assert comp.video_codec == "libx264"
    assert comp.video_profile == "high"
    assert comp.video_level == "4.1"
    assert comp.video_pix_fmt == "yuv420p"
    assert comp.audio_codec == "aac"
    assert comp.audio_bitrate == "192k"
    assert comp.audio_sample_rate == 48000
    assert comp.target_lufs == -14.0


def test_sourcing_and_budget_defaults():
    """Verify jitter settings and script word budget constraints."""
    sourcing = SourcingConfig()
    assert sourcing.jitter_min_sec == 2.0
    assert sourcing.jitter_max_sec == 5.0
    assert sourcing.request_timeout_sec == 30

    budget = ScriptBudgetConfig()
    assert budget.min_words_per_sec == 2.5
    assert budget.max_words_per_sec == 3.2
    assert budget.min_scene_sec == 4.0
    assert budget.max_scene_sec == 8.0
    assert budget.min_cv == 0.4


def test_get_config_singleton(tmp_path: Path):
    """Verify get_config singleton behavior and reload mechanism."""
    cfg1 = get_config(reload=True)
    cfg2 = get_config()
    assert cfg1 is cfg2

    custom_cfg = get_config(reload=True, base_dir=tmp_path)
    assert custom_cfg.paths.base_dir == tmp_path.resolve()
