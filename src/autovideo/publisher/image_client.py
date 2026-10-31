"""
9Router Text-to-Image Client for Thumbnail Generation (B4).
Interfaces with 9router OpenAI-compatible gateway (/v1/images/generations)
to generate photorealistic, cinematic raw base images for video thumbnails.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import httpx
from PIL import Image

from autovideo.core.settings import SettingsManager

logger = logging.getLogger(__name__)


class ThumbnailImageGenerationError(RuntimeError):
    """Raised when 9router AI image generation fails."""
    pass


class NineRouterImageClient:
    """
    Client for generating AI images through 9router (/v1/images/generations).
    Supports providers like Antigravity (e.g. ag/gemini-3.8-flash), OpenAI Codex, etc.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self.timeout_sec = timeout_sec

    def _resolve_config(self) -> tuple[str, str, str]:
        """Resolves API key, base URL, and model from settings or env."""
        sm = SettingsManager()
        s = sm.get_settings()

        api_key = self._api_key if self._api_key is not None else (s.ninerouter_api_key or os.getenv("NINEROUTER_API_KEY", ""))
        base_url = (self._base_url if self._base_url is not None else (s.ninerouter_base_url or os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1"))).rstrip("/")
        
        # Priority for model: explicit arg > image_model setting > ag llm_model > ag/gemini-3.8-flash
        model = self._model or getattr(s, "image_model", None)
        if not model:
            if s.llm_model and s.llm_model.startswith("ag/"):
                model = s.llm_model
            else:
                model = "ag/gemini-3.8-flash"

        return api_key, base_url, model

    def generate_image(
        self,
        prompt: str,
        output_path: Union[Path, str],
        size: str = "1792x1024",
        model: Optional[str] = None,
    ) -> Path:
        """
        Calls 9router to generate an image from prompt and saves it to output_path.

        Args:
            prompt: Text prompt describing the desired image.
            output_path: Destination file path (e.g. renders/{id}/thumbnail_raw.jpg).
            size: Desired image dimensions (e.g. 1792x1024 or 1024x1024).
            model: Optional model override.

        Returns:
            Path to the saved raw image file.
        """
        api_key, base_url, default_model = self._resolve_config()
        target_model = model or default_model

        if not api_key:
            raise ThumbnailImageGenerationError(
                "Chưa cấu hình 9Router API Key trong Cài Đặt! "
                "Không thể vẽ ảnh thumbnail bằng AI khi thiếu API Key."
            )

        endpoint = f"{base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "model": target_model,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }

        logger.info("Calling 9Router Image Generation with model '%s' for prompt: %.80s...", target_model, prompt)

        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                res = client.post(endpoint, headers=headers, json=payload)
        except httpx.ConnectError as ce:
            raise ThumbnailImageGenerationError(
                f"Không thể kết nối đến cổng 9Router tại {endpoint}: {ce}. "
                "Vui lòng kiểm tra 9Router Gateway có đang chạy hay không."
            ) from ce
        except httpx.TimeoutException as te:
            raise ThumbnailImageGenerationError(
                f"Quá thời gian chờ ({self.timeout_sec}s) khi yêu cầu 9Router vẽ ảnh: {te}."
            ) from te
        except Exception as ex:
            raise ThumbnailImageGenerationError(f"Lỗi khi gửi yêu cầu vẽ ảnh tới 9Router: {ex}") from ex

        if res.status_code != 200:
            raise ThumbnailImageGenerationError(
                f"9Router Image Generation thất bại (HTTP {res.status_code}): {res.text} "
                f"[Endpoint: {endpoint}, Model: {target_model}]"
            )

        try:
            resp_data = res.json()
        except Exception as je:
            raise ThumbnailImageGenerationError(f"Phản hồi từ 9Router không phải JSON hợp lệ: {res.text[:200]}") from je

        items = resp_data.get("data")
        if not items or not isinstance(items, list):
            raise ThumbnailImageGenerationError(
                f"Phản hồi từ 9Router không chứa danh sách 'data' ảnh hợp lệ: {resp_data}"
            )

        item = items[0]
        b64_data = item.get("b64_json")
        image_url = item.get("url")

        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if b64_data:
            try:
                img_bytes = base64.b64decode(b64_data)
                out_file.write_bytes(img_bytes)
            except Exception as b64_err:
                raise ThumbnailImageGenerationError(f"Không thể giải mã dữ liệu ảnh base64 từ 9Router: {b64_err}") from b64_err
        elif image_url:
            try:
                with httpx.Client(timeout=30.0) as dl_client:
                    dl_res = dl_client.get(image_url)
                    if dl_res.status_code != 200:
                        raise ThumbnailImageGenerationError(f"Không thể tải ảnh từ URL do 9Router cung cấp: HTTP {dl_res.status_code}")
                    out_file.write_bytes(dl_res.content)
            except Exception as dl_err:
                raise ThumbnailImageGenerationError(f"Lỗi khi tải ảnh từ URL {image_url}: {dl_err}") from dl_err
        else:
            raise ThumbnailImageGenerationError(f"Mục dữ liệu ảnh từ 9Router không chứa b64_json hoặc url: {item}")

        # Validate that the saved file is a valid image
        try:
            with Image.open(out_file) as test_img:
                test_img.verify()
        except Exception as img_err:
            raise ThumbnailImageGenerationError(f"Tệp ảnh do 9Router sinh ra bị lỗi hoặc không thể đọc được: {img_err}") from img_err

        logger.info("Successfully generated thumbnail raw image at: %s (size: %d bytes)", out_file, out_file.stat().st_size)
        return out_file
