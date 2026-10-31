"""
MaziaoTTS Fallback Adapter (REQ-B2-03, docs/maziao.md).
Provides cloud-based Vietnamese text-to-speech fallback using Maziao API.
Supports paragraph / subtitle modes, polling task status, exponential retry,
and offline mock mode for testing without external costs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from autovideo.voiceover.timing_probe import TimingProbe
from autovideo.voiceover.zerotts_adapter import SynthesisResult

logger = logging.getLogger(__name__)


class MaziaoError(Exception):
    """Base exception for Maziao API errors."""
    pass


class MaziaoAPIError(MaziaoError):
    """Raised when Maziao returns an error status code or failure payload."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"Maziao API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message


class MaziaoTimeoutError(MaziaoError):
    """Raised when TTS generation exceeds maximum wait time."""
    pass


@dataclass
class MaziaoTTSConfig:
    """Configuration for Maziao TTS API."""
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("MAZIAO_API_KEY", "")
    )
    base_url: str = "https://api.maziao.com"
    model_id: str = "lingual_speech_v2"
    voice_id: str = "zv_vi_sg_male_thien_tam"
    speed: float = 1.0
    volume: float = 1.0
    pitch: float = 1.0
    export_srt: bool = False
    timeout_sec: float = 30.0
    poll_interval_sec: float = 1.0
    max_poll_retries: int = 40
    mock_mode: bool = False


class MaziaoTTSAdapter:
    """
    Adapter for Maziao Text-to-Speech API.
    Interacts with POST /api/tts/submit and POST /api/tts/status.
    """

    def __init__(
        self,
        config: Optional[MaziaoTTSConfig] = None,
        session: Optional[requests.Session] = None,
        timing_probe: Optional[TimingProbe] = None,
    ):
        self.config = config or MaziaoTTSConfig()
        self.session = session or requests.Session()
        self._timing_probe = timing_probe or TimingProbe()

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers["x-api-key"] = self.config.api_key
        return headers

    def build_submit_payload(
        self,
        text: str,
        mode: str = "paragraph",
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Construct the request body for /api/tts/submit."""
        selected_voice = voice_id or self.config.voice_id
        selected_speed = speed if speed is not None else self.config.speed

        part_item: Dict[str, Any] = {"text": text}
        if mode == "subtitle":
            part_item["startTime"] = start_time
            part_item["endTime"] = end_time if end_time is not None else (start_time + 4.0)

        payload: Dict[str, Any] = {
            "mode": mode,
            "parts": [part_item],
            "voiceId": selected_voice,
            "previewText": text[:100],
            "config": {
                "speed": selected_speed,
                "volume": self.config.volume,
                "pitch": self.config.pitch,
                "export_srt": self.config.export_srt,
            },
            "modelId": self.config.model_id,
        }
        return payload

    def submit_task(
        self,
        text: str,
        mode: str = "paragraph",
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> str:
        """
        Submits TTS task to Maziao API and returns taskId.
        """
        if not self.config.mock_mode and not self.config.api_key:
            raise ValueError("Chưa cấu hình Maziao API Key trong Cài đặt! Vui lòng nhập API Key để tạo giọng đọc Maziao.")
        if self.config.mock_mode:
            return f"mock_task_{abs(hash(text)) % 1000000}"

        url = f"{self.config.base_url.rstrip('/')}/api/tts/submit"
        payload = self.build_submit_payload(text, mode=mode, voice_id=voice_id, speed=speed)

        resp = self._request_with_retry("POST", url, json=payload)
        data = resp.json()

        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise MaziaoAPIError(resp.status_code, f"No taskId in response: {data}")
        return task_id

    def check_status(self, task_id: str) -> Dict[str, Any]:
        """
        Polls /api/tts/status for the given task_id.
        Returns the task item dictionary containing status and resultUrl.
        """
        if not self.config.mock_mode and not self.config.api_key:
            raise ValueError("Chưa cấu hình Maziao API Key trong Cài đặt! Vui lòng nhập API Key để tạo giọng đọc Maziao.")
        if self.config.mock_mode:
            return {
                "id": task_id,
                "status": "completed",
                "resultUrl": f"mock://maziao/{task_id}.wav",
            }

        url = f"{self.config.base_url.rstrip('/')}/api/tts/status"
        payload = {"ids": [task_id]}

        resp = self._request_with_retry("POST", url, json=payload)
        data = resp.json()

        items = data.get("data", [])
        if not items:
            raise MaziaoAPIError(resp.status_code, f"Empty status data: {data}")
        return items[0]

    def poll_until_complete(self, task_id: str) -> str:
        """
        Poll status until task is completed, returning the resultUrl.
        """
        if not self.config.mock_mode and not self.config.api_key:
            raise ValueError("Chưa cấu hình Maziao API Key trong Cài đặt! Vui lòng nhập API Key để tạo giọng đọc Maziao.")
        if self.config.mock_mode:
            return f"mock://maziao/{task_id}.wav"

        for _ in range(self.config.max_poll_retries):
            task_info = self.check_status(task_id)
            status = task_info.get("status", "").lower()

            if status == "completed":
                result_url = task_info.get("resultUrl")
                if not result_url:
                    raise MaziaoAPIError(200, f"Task completed but missing resultUrl: {task_info}")
                return result_url

            if status in ("failed", "error", "cancelled"):
                raise MaziaoAPIError(400, f"TTS task {task_id} failed with status: {status}")

            time.sleep(self.config.poll_interval_sec)

        raise MaziaoTimeoutError(
            f"TTS task {task_id} did not complete within {self.config.max_poll_retries * self.config.poll_interval_sec}s."
        )

    def download_audio(self, url: str, output_path: Path) -> Path:
        """Download synthesized audio file to local path."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if url.startswith("mock://") or self.config.mock_mode:
            if not self.config.mock_mode:
                raise RuntimeError("Phát hiện URL âm thanh mock nhưng chế độ mock bị tắt.")
            # Deterministic mock file generation for testing
            from autovideo.voiceover.zerotts_adapter import TTSVoiceConfig, ZeroTTSAdapter
            zero = ZeroTTSAdapter(config=TTSVoiceConfig(mock_mode=True))
            zero.synthesize(text="Nội dung kiểm thử Maziao fallback", output_path=output_path)
            return output_path

        if not self.config.api_key:
            raise ValueError("Chưa cấu hình Maziao API Key để tải audio!")

        resp = self.session.get(url, stream=True, timeout=self.config.timeout_sec)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return output_path

    def synthesize(
        self,
        text: str,
        output_path: Path | str,
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SynthesisResult:
        """
        High-level synthesis method: submits task, polls for completion,
        downloads audio, and probes duration.
        """
        dest = Path(output_path).resolve()
        selected_voice = voice_id or self.config.voice_id

        task_id = self.submit_task(text=text, voice_id=selected_voice, speed=speed)
        result_url = self.poll_until_complete(task_id)
        self.download_audio(result_url, dest)

        probe = self._timing_probe.probe(dest)

        return SynthesisResult(
            audio_path=dest,
            duration_sec=probe.duration_sec,
            duration_ms=probe.duration_ms,
            text=text,
            voice_id=selected_voice,
            sample_rate=probe.sample_rate or 24000,
            engine="maziao",
        )

    def _request_with_retry(
        self,
        method: str,
        url: str,
        retries: int = 3,
        backoff_sec: float = 1.0,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute HTTP request with retry logic for transient errors."""
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=self.config.timeout_sec,
                    **kwargs,
                )
                if resp.status_code < 400:
                    return resp
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(backoff_sec * (2 ** attempt))
                    continue
                # Client error (e.g., 400, 401, 403)
                raise MaziaoAPIError(resp.status_code, resp.text)
            except (requests.RequestException, OSError) as exc:
                last_exc = exc
                time.sleep(backoff_sec * (2 ** attempt))

        if last_exc:
            raise MaziaoAPIError(500, f"Network request failed after {retries} retries: {last_exc}")
        raise MaziaoAPIError(500, f"Request to {url} failed after {retries} retries.")
