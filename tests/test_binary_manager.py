"""
Unit tests for autovideo.core.binary_manager.
Tests discovery priority (bin/ vs PATH), version parsing, error handling, and requirements checking.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from autovideo.core.config import AppConfig
from autovideo.core.binary_manager import (
    BinaryInfo,
    BinaryManager,
    BinaryNotFoundError,
)


def test_binary_info_model():
    """Verify BinaryInfo data structure and serialization."""
    info = BinaryInfo(
        name="ffmpeg",
        path=Path("/bin/ffmpeg.exe"),
        is_available=True,
        version="6.1.1",
        source="bin",
    )
    assert info.name == "ffmpeg"
    assert info.is_available is True
    assert info.version == "6.1.1"
    assert info.source == "bin"

    d = info.to_dict()
    assert d["name"] == "ffmpeg"
    assert d["source"] == "bin"
    assert d["is_available"] is True


def test_resolution_priority_local_bin_over_path(tmp_path: Path):
    """Verify that a binary located in bin/ takes precedence over system PATH."""
    config = AppConfig.from_base_dir(tmp_path)
    config.ensure_directories()

    # Create dummy executable in bin/
    fake_ffmpeg = config.paths.bin_dir / "ffmpeg.exe"
    fake_ffmpeg.write_text("mock binary content")

    manager = BinaryManager(config=config)

    with patch("shutil.which", return_value="C:\\System32\\ffmpeg.exe"):
        path, source = manager.find_binary("ffmpeg")
        assert path == fake_ffmpeg.resolve()
        assert source == "bin"


def test_resolution_fallback_to_system_path(tmp_path: Path):
    """Verify fallback to system PATH when binary is absent from bin/."""
    config = AppConfig.from_base_dir(tmp_path)
    config.ensure_directories()
    # Note: bin/ is empty

    manager = BinaryManager(config=config)

    with patch("shutil.which", return_value="C:\\tools\\yt-dlp.exe"):
        path, source = manager.find_binary("yt-dlp")
        assert path == Path("C:\\tools\\yt-dlp.exe").resolve()
        assert source == "system"


def test_missing_binary_handling(tmp_path: Path):
    """Verify missing binary returns is_available=False without error."""
    config = AppConfig.from_base_dir(tmp_path)
    manager = BinaryManager(config=config)

    with patch("shutil.which", return_value=None):
        info = manager.check_binary("nonexistent_binary_xyz")
        assert info.is_available is False
        assert info.path is None
        assert info.version is None
        assert info.source == "missing"


def test_require_raises_on_missing(tmp_path: Path):
    """Verify require() raises descriptive BinaryNotFoundError on missing binary."""
    config = AppConfig.from_base_dir(tmp_path)
    manager = BinaryManager(config=config)

    with patch("shutil.which", return_value=None):
        with pytest.raises(BinaryNotFoundError) as exc_info:
            manager.require("missing_binary_abc")
        assert "missing_binary_abc" in str(exc_info.value)
        assert str(config.paths.bin_dir) in str(exc_info.value)


def test_version_extraction_regex():
    """Verify version parser against outputs from ffmpeg, yt-dlp, BBDown."""
    manager = BinaryManager()

    # FFmpeg sample output
    ffmpeg_out = "ffmpeg version 7.0.2-full_build-www.gyan.dev Copyright (c) 2000-2024"
    assert manager._extract_version_from_output("ffmpeg", ffmpeg_out) == "7.0.2-full_build-www.gyan.dev"

    # FFprobe sample output
    ffprobe_out = "ffprobe version N-112345-g897abc Copyright (c) 2007-2024"
    assert manager._extract_version_from_output("ffprobe", ffprobe_out) == "N-112345-g897abc"

    # yt-dlp sample output
    ytdlp_out = "2024.08.06\n"
    assert manager._extract_version_from_output("yt-dlp", ytdlp_out) == "2024.08.06"

    # BBDown sample output
    bbdown_out = "BBDown v1.6.2 (c) 2023"
    assert manager._extract_version_from_output("BBDown", bbdown_out) == "1.6.2"


def test_is_ready_predicate(tmp_path: Path):
    """Verify is_ready correctly evaluates required binaries."""
    config = AppConfig.from_base_dir(tmp_path)
    manager = BinaryManager(config=config)

    # Mock all missing
    with patch("shutil.which", return_value=None):
        assert manager.is_ready(("ffmpeg", "ffprobe")) is False

    # Mock ffmpeg present, ffprobe missing
    def mock_which(name: str):
        if "ffmpeg" in name:
            return "C:\\bin\\ffmpeg.exe"
        return None

    with patch("shutil.which", side_effect=mock_which):
        with patch.object(BinaryManager, "probe_version", return_value="7.0"):
            assert manager.is_ready(("ffmpeg", "ffprobe")) is False
            assert manager.is_ready(("ffmpeg",)) is True


def test_real_system_detection():
    """Integration check on current host: ffmpeg or ffprobe if installed in system."""
    manager = BinaryManager()
    all_status = manager.check_all()

    assert "ffmpeg" in all_status
    assert "ffprobe" in all_status
    assert "BBDown" in all_status
    assert "yt-dlp" in all_status

    # Check that status objects are valid
    for name, info in all_status.items():
        assert isinstance(info, BinaryInfo)
        assert info.name == name
        if info.is_available:
            assert info.path is not None
            assert info.version is not None
            assert info.source in ("bin", "system")
        else:
            assert info.source == "missing"
