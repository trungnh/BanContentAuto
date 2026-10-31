"""
Verification Tests for:
1. Elimination of mock/fallback in pipeline.py (Fail-Fast Verification).
2. NineRouterImageClient Text-to-Image for Thumbnail generation.
3. Dynamic, un-hardcoded SEOPackager title and tag generation.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from autovideo.publisher.image_client import (
    NineRouterImageClient,
    ThumbnailImageGenerationError,
)
from autovideo.publisher.manager import PublisherManager
from autovideo.publisher.seo_packager import SEOPackage, SEOPackager
from autovideo.script.pipeline import (
    GeminiFlashAdapter,
    NineRouterAdapter,
    ScriptwritingPipeline,
    parse_scenes_payload,
    parse_seo_payload,
)


def _create_sample_base64_image() -> str:
    """Helper creating small valid JPEG base64 string."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ==============================================================================
# 1. FAIL-FAST TESTS (NO SILENT MOCK / FALLBACK)
# ==============================================================================

def test_ninerouter_adapter_raises_on_missing_api_key():
    """NineRouterAdapter must raise ValueError when API key is missing, never fallback."""
    adapter = NineRouterAdapter(api_key="", base_url="http://localhost:20128/v1")
    with pytest.raises(ValueError, match="Chưa cấu hình 9Router API Key"):
        adapter.generate("Hello world")


def test_ninerouter_adapter_raises_on_http_error():
    """NineRouterAdapter must raise RuntimeError on API failure, never fallback."""
    adapter = NineRouterAdapter(api_key="test_key", base_url="http://localhost:20128/v1")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="9Router API lỗi"):
            adapter.generate("Test prompt")


def test_gemini_adapter_raises_on_missing_api_key():
    """GeminiFlashAdapter must raise ValueError when API key is missing."""
    adapter = GeminiFlashAdapter(api_key="")
    with pytest.raises(ValueError, match="Chưa cấu hình Gemini API Key"):
        adapter.generate("Hello world")


def test_gemini_adapter_raises_on_http_error():
    """GeminiFlashAdapter must raise RuntimeError on API failure."""
    adapter = GeminiFlashAdapter(api_key="test_key")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Permission Denied"
    
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Gemini API lỗi"):
            adapter.generate("Test prompt")


def test_parse_scenes_payload_fails_fast_on_invalid_output():
    """parse_scenes_payload must raise ValueError when output is not valid JSON, never return dummy scenes."""
    invalid_outputs = [
        "Xin chào, tôi là trợ lý AI và đây là ý tưởng của tôi...",
        "```text\nĐây không phải là JSON\n```",
        "Tập lệnh bị lỗi kết nối hoặc rate limit",
    ]
    for bad_text in invalid_outputs:
        with pytest.raises(ValueError, match="không trả về danh sách phân cảnh hợp lệ"):
            parse_scenes_payload(bad_text, topic="Chủ đề kiểm tra")


def test_parse_seo_payload_fails_fast_on_invalid_output():
    """parse_seo_payload must raise ValueError when output is not valid JSON, never return canned titles."""
    invalid_outputs = [
        "Không thể tạo SEO lúc này.",
        "```html\n<h1>Lỗi</h1>\n```",
        "Error 429 Quota Exceeded",
    ]
    for bad_text in invalid_outputs:
        with pytest.raises(ValueError, match="không trả về gói SEO hợp lệ"):
            parse_seo_payload(bad_text, topic="Chủ đề kiểm tra")


def test_pipeline_generate_screenplay_fails_fast_if_seo_missing_titles():
    """Pipeline raises ValueError if LLM response misses 'titles' in SEO."""
    mock_adapter = MagicMock()
    # 1st call for scenes -> valid scenes JSON
    scenes_json = json.dumps([
        {
            "scene_id": "SCENE_001",
            "text": "Đây là câu mở đầu phân cảnh số một kết thúc rõ ràng.",
            "duration_sec": 5.0,
            "word_count": 12,
            "visual_prompt": "Test visual prompt",
            "keywords": {"vi": ["test"], "en": ["test"], "zh": []},
        }
    ])
    # 2nd call for SEO -> missing titles
    seo_missing_titles = json.dumps({
        "description": "Mô tả đầy đủ nhưng thiếu titles",
    })
    mock_adapter.generate.side_effect = [scenes_json, seo_missing_titles]

    pipeline = ScriptwritingPipeline(adapter=mock_adapter)
    with pytest.raises(ValueError, match="không trả về danh sách tiêu đề"):
        pipeline.generate_screenplay(topic="Chủ đề thiếu tiêu đề")


# ==============================================================================
# 2. 9ROUTER TEXT-TO-IMAGE CLIENT TESTS
# ==============================================================================

def test_image_client_raises_on_missing_api_key(tmp_path: Path):
    """NineRouterImageClient must raise ThumbnailImageGenerationError when API key is missing."""
    client = NineRouterImageClient(api_key="", base_url="http://localhost:20128/v1")
    with pytest.raises(ThumbnailImageGenerationError, match="Chưa cấu hình 9Router API Key"):
        client.generate_image("Test prompt", tmp_path / "thumb.jpg")


def test_image_client_raises_on_network_connect_error(tmp_path: Path):
    """NineRouterImageClient raises ThumbnailImageGenerationError on connection error."""
    client = NineRouterImageClient(api_key="test_key", base_url="http://invalid-local-domain:99999/v1")
    with pytest.raises(ThumbnailImageGenerationError, match="Không thể kết nối đến cổng 9Router"):
        client.generate_image("Test prompt", tmp_path / "thumb.jpg")


def test_image_client_success_base64(tmp_path: Path):
    """NineRouterImageClient successfully decodes b64_json and writes valid image."""
    client = NineRouterImageClient(api_key="test_key", base_url="http://localhost:20128/v1")
    
    b64_str = _create_sample_base64_image()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "created": 1234567,
        "data": [{"b64_json": b64_str}],
    }

    out_file = tmp_path / "test_thumb_raw.jpg"
    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.generate_image("A dramatic wild animal", out_file)
        assert res.exists()
        assert res.stat().st_size > 0
        with Image.open(res) as img:
            assert img.size == (100, 100)


# ==============================================================================
# 3. DYNAMIC SEO & PUBLISHER UN-HARDCODED TESTS
# ==============================================================================

def test_seo_packager_no_hardcoded_clickbait():
    """SEOPackager does not use hardcoded clickbait titles."""
    packager = SEOPackager()
    pkg = packager.generate_package(
        project_id="PROJ_UNHARDCODED",
        topic="Sự Thật Về Loài Cá Voi Sát Thủ",
        chapters=[],
    )
    for t in pkg.titles:
        assert "Sự Thật Chấn Động Đằng Sau Mọi Câu Chuyện" not in t
        assert "Đi Tìm Câu Trả Lời Cho Bí Ẩn Lớn Nhất" not in t
        assert "Nghịch Lý Đen Tối Và Lời Cảnh Tỉnh Cần Biết" not in t
        assert "Toàn Bộ Sự Thật Chưa Từng Tiết Lộ" not in t


def test_seo_packager_no_hardcoded_generic_tags():
    """SEOPackager does not inject hardcoded generic tags like 'bancontent' or 'autovideo studio'."""
    packager = SEOPackager()
    pkg = packager.generate_package(
        project_id="PROJ_UNHARDCODED",
        topic="Sự Thật Về Loài Cá Voi Sát Thủ",
        chapters=[],
    )
    assert "bancontent" not in pkg.tags
    assert "autovideo studio" not in pkg.tags
    assert "câu chuyện bí ẩn" not in pkg.tags
    assert "#BanContentAuto" not in pkg.hashtags
