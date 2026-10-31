"""
Unit and integration tests for Asset Sourcing Engine (WU-02).
Tests A_Bogus signature generation, Douyin link extraction, redirect resolution,
watermark removal (/playwm/ -> /play/), duration filtering (8s-60s),
rate-limit retries, BBDown wrapper, and Unified Dispatcher routing.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import httpx

from autovideo.core.config import AppConfig
from autovideo.sourcing.a_bogus import ABogusSigner, BOGUS_CHARS
from autovideo.sourcing.bilibili import (
    BilibiliDownloader,
    BilibiliDownloaderError,
    BilibiliVideoInfo,
)
from autovideo.sourcing.douyin import (
    CleanVideoInfo,
    DouyinExtractor,
    DouyinExtractorError,
    DurationOutOfRangeError,
    RateLimitError,
    VideoNotFoundError,
)
from autovideo.sourcing.engine import AssetSourcingEngine, SourcedAsset
from autovideo.sourcing.universal import (
    DurationFilteredError,
    UniversalDownloader,
    UniversalDownloaderError,
    UniversalVideoInfo,
)


# ============================================================================
# 1. A_Bogus Pure-Python Signer Tests
# ============================================================================

def test_a_bogus_token_generation():
    """Verify ABogusSigner generates a valid, non-empty, URL-safe signature token."""
    signer = ABogusSigner()
    query = {"aweme_id": "7123456789012345678", "aid": "6383", "device_platform": "webapp"}

    # Fixed timestamp for determinism
    token1 = signer.generate_a_bogus(query=query, timestamp=1700000000000)
    token2 = signer.generate_a_bogus(query=query, timestamp=1700000000000)

    assert isinstance(token1, str)
    assert len(token1) >= 40
    assert token1 == token2, "A_Bogus generation must be deterministic for identical inputs"

    # All characters must belong to custom alphabet or padding '='
    allowed_chars = set(BOGUS_CHARS + "=")
    assert all(c in allowed_chars for c in token1)


def test_a_bogus_query_normalization():
    """Verify dict and query string representations produce equivalent signatures."""
    signer = ABogusSigner()
    dict_query = {"b": "2", "a": "1"}
    str_query = "a=1&b=2"
    fixed_ts = 1715000000000

    token_dict = signer.generate_a_bogus(dict_query, timestamp=fixed_ts)
    token_str = signer.generate_a_bogus(str_query, timestamp=fixed_ts)

    assert token_dict == token_str


def test_a_bogus_sign_url():
    """Verify sign_url appends a_bogus query parameter without corrupting URL."""
    signer = ABogusSigner()
    base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
    signed = signer.sign_url(base_url, params={"aweme_id": "12345"}, timestamp=1710000000000)

    assert "https://www.douyin.com/aweme/v1/web/aweme/detail/" in signed
    assert "aweme_id=12345" in signed
    assert "a_bogus=" in signed


# ============================================================================
# 2. Douyin Link Extraction Tests
# ============================================================================

@pytest.mark.parametrize(
    "input_text,expected_url",
    [
        (
            "https://v.douyin.com/iRoF123/",
            "https://v.douyin.com/iRoF123/",
        ),
        (
            "https://www.douyin.com/video/7391234567890123456",
            "https://www.douyin.com/video/7391234567890123456",
        ),
        (
            "7.12 复制打开抖音，看看【小明惊险瞬间】 https://v.douyin.com/iRoF123/ 04/23 l@s.ok :4pm",
            "https://v.douyin.com/iRoF123/",
        ),
        (
            "Check this out: https://www.douyin.com/video/7123456789012345678?modal_id=7123456789012345678",
            "https://www.douyin.com/video/7123456789012345678",
        ),
    ],
)
def test_extract_douyin_url_formats(input_text, expected_url):
    """Verify URL extraction from raw URLs and embedded Chinese share text."""
    extracted = DouyinExtractor.extract_douyin_url(input_text)
    assert extracted == expected_url


def test_extract_douyin_url_none():
    """Verify non-Douyin text returns None."""
    assert DouyinExtractor.extract_douyin_url("Random text without links") is None
    assert DouyinExtractor.extract_douyin_url("https://www.youtube.com/watch?v=123") is None


# ============================================================================
# 3. Aweme ID Resolution Tests
# ============================================================================

def test_resolve_aweme_id_direct():
    """Direct video URL should extract aweme_id without network requests."""
    extractor = DouyinExtractor()
    aweme_id = extractor.resolve_aweme_id("https://www.douyin.com/video/7391234567890123456")
    assert aweme_id == "7391234567890123456"


def test_resolve_aweme_id_from_redirect():
    """Short URL should follow HTTP 302 redirect and extract ID from Location header."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.headers = {"Location": "https://www.douyin.com/video/7399999999999999999?previous_page=app_code"}
    mock_client.get.return_value = mock_resp
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    extractor = DouyinExtractor(http_client=mock_client)
    aweme_id = extractor.resolve_aweme_id("https://v.douyin.com/iRoF888/")

    assert aweme_id == "7399999999999999999"


def test_resolve_aweme_id_invalid():
    """Invalid input should raise VideoNotFoundError."""
    extractor = DouyinExtractor()
    with pytest.raises(VideoNotFoundError):
        extractor.resolve_aweme_id("invalid input string")


# ============================================================================
# 4. Detail Parsing & Watermark Stripping Tests
# ============================================================================

def test_extract_clean_video_url_watermark_removal():
    """Verify /playwm/ in play_addr is rewritten to /play/ for watermark stripping."""
    extractor = DouyinExtractor()
    sample_payload = {
        "aweme_detail": {
            "aweme_id": "7123456789",
            "desc": "Car crash footage",
            "video": {
                "duration": 15000,  # 15s in ms
                "width": 1080,
                "height": 1920,
                "play_addr": {
                    "url_list": [
                        "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0200fg10000&ratio=720p",
                    ]
                },
            },
        }
    }

    clean_info = extractor.extract_clean_video_url(sample_payload)
    assert "/playwm/" not in clean_info.clean_url
    assert "/play/" in clean_info.clean_url
    assert clean_info.duration_sec == 15.0
    assert clean_info.is_valid_duration is True


def test_extract_clean_video_url_highest_bitrate():
    """Verify extractor chooses stream with highest bitrate."""
    extractor = DouyinExtractor()
    sample_payload = {
        "aweme_detail": {
            "aweme_id": "7123456789",
            "desc": "High bitrate test",
            "video": {
                "duration": 20000,
                "width": 1080,
                "height": 1920,
                "bit_rate": [
                    {
                        "bit_rate": 800000,
                        "play_addr": {"url_list": ["https://cdn.douyin.com/video/800k.mp4"]},
                    },
                    {
                        "bit_rate": 2500000,
                        "play_addr": {"url_list": ["https://cdn.douyin.com/video/2500k.mp4"]},
                    },
                    {
                        "bit_rate": 1200000,
                        "play_addr": {"url_list": ["https://cdn.douyin.com/video/1200k.mp4"]},
                    },
                ],
            },
        }
    }

    clean_info = extractor.extract_clean_video_url(sample_payload)
    assert clean_info.bitrate == 2500000
    assert clean_info.clean_url == "https://cdn.douyin.com/video/2500k.mp4"


# ============================================================================
# 5. Duration Filtering Tests (REQ-B2-02)
# ============================================================================

def test_duration_filtering_too_short():
    """Clips under 8s must be rejected per REQ-B2-02."""
    extractor = DouyinExtractor()
    payload = {
        "aweme_detail": {
            "aweme_id": "short_1",
            "video": {
                "duration": 5000,  # 5s
                "play_addr": {"url_list": ["https://cdn.douyin.com/video/short.mp4"]},
            },
        }
    }

    with pytest.raises(DurationOutOfRangeError):
        extractor.extract_clean_video_url(payload, enforce_duration=True)


def test_duration_filtering_too_long():
    """Clips over 60s must be rejected per REQ-B2-02."""
    extractor = DouyinExtractor()
    payload = {
        "aweme_detail": {
            "aweme_id": "long_1",
            "video": {
                "duration": 75000,  # 75s
                "play_addr": {"url_list": ["https://cdn.douyin.com/video/long.mp4"]},
            },
        }
    }

    with pytest.raises(DurationOutOfRangeError):
        extractor.extract_clean_video_url(payload, enforce_duration=True)


def test_duration_filtering_valid():
    """Clips between 8s and 60s are accepted."""
    extractor = DouyinExtractor()
    payload = {
        "aweme_detail": {
            "aweme_id": "valid_1",
            "video": {
                "duration": 24000,  # 24s
                "play_addr": {"url_list": ["https://cdn.douyin.com/video/valid.mp4"]},
            },
        }
    }

    info = extractor.extract_clean_video_url(payload, enforce_duration=True)
    assert info.duration_sec == 24.0
    assert info.is_valid_duration is True


# ============================================================================
# 6. Jitter Delay & Stream Download Tests
# ============================================================================

def test_download_video_stream(tmp_path: Path):
    """Verify video streaming download writes content correctly to cache/raw_footage/."""
    dummy_video_bytes = b"\x00\x00\x00 ftypisom" + (b"video_bytes_data" * 100)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = [dummy_video_bytes]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_resp
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    extractor = DouyinExtractor(http_client=mock_client)
    dest_file = tmp_path / "raw_footage" / "test_video.mp4"

    saved_path = extractor.download_video(
        clean_url="https://mock.cdn/video.mp4",
        output_path=dest_file,
        apply_jitter=False,  # Skip delay for rapid unit test
    )

    assert saved_path.exists()
    assert saved_path.stat().st_size == len(dummy_video_bytes)


def test_fetch_detail_rate_limit_retry():
    """Verify API handles HTTP 429 with retries before succeeding."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "aweme_detail": {"aweme_id": "retry_123", "video": {"duration": 12000}}
    }

    mock_client = MagicMock()
    mock_client.get.side_effect = [mock_resp_429, mock_resp_200]
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    with patch("time.sleep", return_value=None):
        extractor = DouyinExtractor(http_client=mock_client)
        detail = extractor.fetch_video_detail("retry_123")
        assert detail["aweme_detail"]["aweme_id"] == "retry_123"
        assert mock_client.get.call_count == 2


# ============================================================================
# 7. Bilibili Downloader Tests
# ============================================================================

def test_extract_bvid():
    """Verify BVID extraction from raw string or Bilibili URL."""
    assert BilibiliDownloader.extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"
    assert (
        BilibiliDownloader.extract_bvid("https://www.bilibili.com/video/BV1Q5411W7d8?spm_id_from=333.337")
        == "BV1Q5411W7d8"
    )
    assert BilibiliDownloader.extract_bvid("no bvid here") is None


def test_bilibili_bbdown_mock(tmp_path: Path):
    """When BBDown is available and succeeds, use BBDown."""
    mock_bin_mgr = MagicMock()
    mock_bin_info = MagicMock()
    mock_bin_info.is_available = True
    mock_bin_info.path = Path("bin/BBDown.exe")
    mock_bin_mgr.get_binary.return_value = mock_bin_info

    downloader = BilibiliDownloader(binary_manager=mock_bin_mgr)

    # Mock subprocess.run to simulate BBDown writing file
    def fake_subprocess_run(cmd, **kwargs):
        out_dir = Path(cmd[3])
        fake_file = out_dir / "sample_video.mp4"
        fake_file.write_bytes(b"mp4content")
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        info = downloader.download("BV1xx411c7mD", output_dir=tmp_path)
        assert info.source_tool == "BBDown"
        assert info.bvid == "BV1xx411c7mD"
        assert info.downloaded_path.exists()


def test_bilibili_ytdlp_fallback(tmp_path: Path):
    """When BBDown is missing, fall back to yt-dlp."""
    mock_bin_mgr = MagicMock()
    mock_bin_info = MagicMock()
    mock_bin_info.is_available = False
    mock_bin_mgr.get_binary.return_value = mock_bin_info

    downloader = BilibiliDownloader(binary_manager=mock_bin_mgr)

    fake_mp4 = tmp_path / "bilibili_BV1Fallback1.mp4"
    fake_mp4.write_bytes(b"ytdlp_data")

    with patch.object(downloader, "_download_via_ytdlp", return_value=fake_mp4):
        info = downloader.download("BV1Fallback1", output_dir=tmp_path)
        assert info.source_tool == "yt-dlp"
        assert info.bvid == "BV1Fallback1"
        assert info.downloaded_path == fake_mp4


# ============================================================================
# 8. Universal Downloader Tests
# ============================================================================

def test_universal_duration_filter(tmp_path: Path):
    """UniversalDownloader rejects clips outside duration bounds."""
    downloader = UniversalDownloader()

    # Probe returns duration = 3.0s (under 8.0s)
    with patch.object(downloader, "get_video_info", return_value={"id": "u1", "duration": 3.0}):
        with pytest.raises(DurationFilteredError):
            downloader.download("https://example.com/short_video.mp4", output_dir=tmp_path)


def test_universal_candidate_duration_selection(tmp_path: Path):
    """UniversalDownloader picks candidate matching duration bounds from search entries."""
    downloader = UniversalDownloader()
    fake_entries = [
        {"id": "doc1", "title": "2-hour documentary", "duration": 7200.0},
        {"id": "clip2", "title": "45s incident clip", "duration": 45.0},
        {"id": "short3", "title": "3s stub", "duration": 3.0},
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "universal_clip2.mp4") as mock_dl:
            res = downloader.download("ytsearch5:incident", output_dir=tmp_path, enforce_duration=True)
            assert res.video_id == "clip2"
            assert res.duration_sec == 45.0
            mock_dl.assert_called_once()


def test_universal_candidate_prefers_hd_resolution(tmp_path: Path):
    """UniversalDownloader prefers candidates with 720p/1080p resolution over low-res clips."""
    downloader = UniversalDownloader()
    fake_entries = [
        {"id": "lowres1", "title": "240p clip", "duration": 30.0, "height": 240, "width": 320},
        {"id": "hd_clip2", "title": "720p HD incident", "duration": 40.0, "height": 720, "width": 1280},
        {"id": "lowres3", "title": "360p clip", "duration": 35.0, "height": 360, "width": 640},
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "universal_hd_clip2.mp4") as mock_dl:
            res = downloader.download("ytsearch8:incident", output_dir=tmp_path, enforce_duration=True)
            assert res.video_id == "hd_clip2"
            assert res.height == 720
            mock_dl.assert_called_once()


def test_universal_rejects_corrupted_file(tmp_path: Path):
    """UniversalDownloader raises UniversalDownloaderError and removes file when verification fails."""
    downloader = UniversalDownloader()
    corrupted_file = tmp_path / "universal_corrupt.mp4"
    corrupted_file.write_bytes(b"corrupted header data")

    with patch("yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.return_value = 0
        with patch.object(downloader, "_verify_video_file", return_value=False):
            with pytest.raises(UniversalDownloaderError, match="bị lỗi/hỏng dữ liệu"):
                downloader._download_and_verify("https://example.com/corrupt", "corrupt", tmp_path)

    assert not corrupted_file.exists()


# ============================================================================
# 9. Unified Asset Sourcing Dispatcher Tests
# ============================================================================

def test_engine_routes_douyin_url(tmp_path: Path):
    """Dispatcher automatically detects Douyin URL and delegates to DouyinExtractor."""
    mock_douyin = MagicMock()
    fake_info = CleanVideoInfo(
        aweme_id="79998888",
        title="Crash scene",
        clean_url="https://clean.cdn/play/1.mp4",
        duration_sec=18.5,
        width=1080,
        height=1920,
        bitrate=2000000,
        cover_url="https://clean.cdn/cover.jpg",
        downloaded_path=tmp_path / "douyin_79998888.mp4",
    )
    mock_douyin.extract_and_download.return_value = fake_info

    engine = AssetSourcingEngine(douyin_extractor=mock_douyin)
    asset = engine.source_scene_asset(
        scene_id=1,
        query="https://www.douyin.com/video/79998888",
        preferred_vault="douyin",
        output_dir=tmp_path,
    )

    assert asset.vault_source == "douyin"
    assert asset.scene_id == 1
    assert asset.duration_sec == 18.5
    assert asset.is_watermark_clean is True
    mock_douyin.extract_and_download.assert_called_once()


def test_engine_routes_bilibili_url(tmp_path: Path):
    """Dispatcher detects Bilibili BVID and routes to BilibiliDownloader."""
    mock_bilibili = MagicMock()
    fake_info = BilibiliVideoInfo(
        bvid="BV1Target99",
        title="Bilibili stunt",
        downloaded_path=tmp_path / "bilibili_BV1Target99.mp4",
        duration_sec=22.0,
        source_tool="BBDown",
    )
    mock_bilibili.download.return_value = fake_info
    mock_bilibili.extract_bvid.return_value = "BV1Target99"

    engine = AssetSourcingEngine(bilibili_downloader=mock_bilibili)
    asset = engine.source_scene_asset(
        scene_id=2,
        query="BV1Target99",
        preferred_vault="bilibili",
        output_dir=tmp_path,
    )

    assert asset.vault_source == "bilibili"
    assert asset.scene_id == 2
    assert asset.is_watermark_clean is True


def test_engine_fallback_cascade(tmp_path: Path):
    """When preferred Douyin vault fails, engine cascades to Universal downloader."""
    mock_douyin = MagicMock()
    mock_douyin.extract_and_download.side_effect = DouyinExtractorError("Douyin blocked")

    mock_universal = MagicMock()
    fake_u_info = UniversalVideoInfo(
        video_id="pexels_123",
        title="Highway dashcam",
        downloaded_path=tmp_path / "universal_pexels_123.mp4",
        duration_sec=14.0,
        extractor="pexels",
        width=1920,
        height=1080,
    )
    mock_universal.download.return_value = fake_u_info

    engine = AssetSourcingEngine(
        douyin_extractor=mock_douyin,
        universal_downloader=mock_universal,
    )

    asset = engine.source_scene_asset(
        scene_id=3,
        query="https://v.douyin.com/fail_link/",
        preferred_vault="douyin",
        output_dir=tmp_path,
    )

    assert asset.vault_source == "universal"
    assert asset.scene_id == 3
    assert asset.duration_sec == 14.0
