"""
Douyin video extractor and downloader.
Extracts clean watermark-free video URLs, handles HTTP 301/302 redirects,
signs requests via pure-Python A_Bogus, enforces duration filters (8s-60s),
and executes downloads with jitter delays and rate-limit retries.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from autovideo.core.config import AppConfig, get_config
from autovideo.sourcing.a_bogus import ABogusSigner, DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

# URL match patterns
DOUYIN_URL_REGEX = re.compile(
    r"https?://(?:v\.douyin\.com/[a-zA-Z0-9_\-]+/?|(?:www\.)?douyin\.com/video/(\d+))"
)
AWEME_ID_REGEX = re.compile(r"/video/(\d+)")
SHORT_LINK_REGEX = re.compile(r"https?://v\.douyin\.com/[a-zA-Z0-9_\-]+/?")

# Douyin Web Detail API Endpoint
DOUYIN_DETAIL_API = "https://www.douyin.com/aweme/v1/web/aweme/detail/"


class DouyinExtractorError(Exception):
    """Base exception for Douyin extraction errors."""
    pass


class VideoNotFoundError(DouyinExtractorError):
    """Raised when aweme_id or video details cannot be resolved."""
    pass


class DurationOutOfRangeError(DouyinExtractorError):
    """Raised when video duration is outside the required range (<8s or >60s)."""
    pass


class RateLimitError(DouyinExtractorError):
    """Raised when Douyin rate-limits the request."""
    pass


@dataclass
class CleanVideoInfo:
    """Metadata and direct stream info for a watermark-free Douyin video."""

    aweme_id: str
    title: str
    clean_url: str
    duration_sec: float
    width: int
    height: int
    bitrate: int
    cover_url: str
    downloaded_path: Optional[Path] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid_duration(self) -> bool:
        """Requirement REQ-B2-02: 8.0s <= duration <= 60.0s."""
        return 8.0 <= self.duration_sec <= 60.0


class DouyinExtractor:
    """
    Extractor and downloader for Douyin videos without watermark.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        http_client: Optional[httpx.Client] = None,
    ):
        self.config = config or get_config()
        self.user_agent = user_agent
        self.signer = ABogusSigner(user_agent=user_agent)
        self._custom_client = http_client
        self._cookies: Dict[str, str] = {}
        self._load_cookies()

    def _get_client(self, follow_redirects: bool = True) -> httpx.Client:
        """Return an HTTP client configured with standard headers and timeouts."""
        if self._custom_client is not None:
            return self._custom_client

        headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        return httpx.Client(
            headers=headers,
            cookies=self._cookies,
            timeout=self.config.sourcing.request_timeout_sec,
            follow_redirects=follow_redirects,
        )

    def _load_cookies(self) -> None:
        """Attempt to load cookies from config/douyin_cookie.yaml or config/cookies.txt."""
        cookie_cfg = self.config.paths.config_dir / "douyin_cookie.yaml"
        if cookie_cfg.exists():
            try:
                import yaml
                with open(cookie_cfg, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            self._cookies[str(k)] = str(v)
            except Exception as e:
                logger.warning(f"Could not parse {cookie_cfg}: {e}")

        cookies_txt = self.config.paths.config_dir / "cookies.txt"
        if cookies_txt.exists() and not self._cookies:
            try:
                with open(cookies_txt, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    for item in content.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            self._cookies[k.strip()] = v.strip()
            except Exception as e:
                logger.warning(f"Could not parse {cookies_txt}: {e}")

    @staticmethod
    def extract_douyin_url(text: str) -> Optional[str]:
        """
        Extract clean Douyin URL from arbitrary text (including Chinese share text).

        Examples:
            - 'https://v.douyin.com/iRoF123/'
            - 'https://www.douyin.com/video/7391234567890123456'
            - '7.12 复制打开抖音... https://v.douyin.com/iRoF123/ 04/23 ...'
        """
        if not text:
            return None
        match = DOUYIN_URL_REGEX.search(text)
        if match:
            return match.group(0)
        return None

    def resolve_aweme_id(self, url_or_text: str) -> str:
        """
        Resolve aweme_id from a URL or share text, following 301/302 redirects if needed.

        Returns:
            aweme_id string.

        Raises:
            VideoNotFoundError: If URL or aweme_id cannot be found.
        """
        clean_url = self.extract_douyin_url(url_or_text)
        if not clean_url:
            # Check if input itself is numeric aweme_id
            if url_or_text.strip().isdigit() and len(url_or_text.strip()) >= 15:
                return url_or_text.strip()
            raise VideoNotFoundError(f"No valid Douyin URL or ID found in: {url_or_text}")

        # Check for direct video ID
        direct_match = AWEME_ID_REGEX.search(clean_url)
        if direct_match:
            return direct_match.group(1)

        # Follow short link redirect (v.douyin.com)
        if "v.douyin.com" in clean_url:
            try:
                # Use client without automatic redirect to inspect 301/302 Location header
                with self._get_client(follow_redirects=False) as client:
                    resp = client.get(clean_url)
                    location = resp.headers.get("Location") or resp.headers.get("location")
                    if location:
                        id_match = AWEME_ID_REGEX.search(str(location))
                        if id_match:
                            return id_match.group(1)

                # Fallback: follow redirect to destination
                with self._get_client(follow_redirects=True) as client:
                    resp = client.get(clean_url)
                    final_url = str(resp.url)
                    id_match = AWEME_ID_REGEX.search(final_url)
                    if id_match:
                        return id_match.group(1)
            except Exception as e:
                raise VideoNotFoundError(f"Failed to follow redirect for {clean_url}: {e}") from e

        raise VideoNotFoundError(f"Could not extract aweme_id from {clean_url}")

    def fetch_video_detail(self, aweme_id: str) -> Dict[str, Any]:
        """
        Query Douyin web/aweme/detail API with signed A_Bogus parameter.

        Args:
            aweme_id: Numerical video identifier.

        Returns:
            JSON dictionary with 'aweme_detail'.

        Raises:
            VideoNotFoundError: If video detail is empty or deleted.
            RateLimitError: If API returned rate-limiting status.
        """
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "aweme_id": aweme_id,
            "update_version_code": "170400",
            "pc_client_type": "1",
            "version_code": "190500",
            "version_name": "19.5.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "126.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "126.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "8",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
        }

        # Sign request parameters with A_Bogus
        a_bogus = self.signer.generate_a_bogus(params)
        params["a_bogus"] = a_bogus

        max_retries = self.config.sourcing.max_retries
        for attempt in range(max_retries):
            try:
                with self._get_client() as client:
                    resp = client.get(DOUYIN_DETAIL_API, params=params)

                if resp.status_code == 429:
                    if attempt < max_retries - 1:
                        sleep_time = (2 ** attempt) * 1.5
                        time.sleep(sleep_time)
                        continue
                    raise RateLimitError("Douyin detail API rate limit (HTTP 429)")

                resp.raise_for_status()
                data = resp.json()

                aweme_detail = data.get("aweme_detail")
                if not aweme_detail:
                    # Some responses return filter_detail or error message
                    if "filter_detail" in data:
                        raise VideoNotFoundError(f"Video {aweme_id} filtered or restricted")
                    raise VideoNotFoundError(f"No aweme_detail returned for {aweme_id}")

                return data

            except httpx.HTTPError as e:
                if attempt < max_retries - 1:
                    time.sleep(1.0 + attempt)
                    continue
                raise DouyinExtractorError(f"HTTP error querying detail for {aweme_id}: {e}") from e

        raise DouyinExtractorError(f"Failed to fetch detail for {aweme_id} after {max_retries} retries")

    def extract_clean_video_url(
        self,
        detail_json: Dict[str, Any],
        enforce_duration: bool = True,
    ) -> CleanVideoInfo:
        """
        Extract direct watermark-free video URL from detail JSON.
        Replaces /playwm/ with /play/ and selects the highest bitrate stream.

        Args:
            detail_json: Raw API response dictionary.
            enforce_duration: If True, raises DurationOutOfRangeError for <8s or >60s.

        Returns:
            CleanVideoInfo object.
        """
        detail = detail_json.get("aweme_detail", detail_json)
        aweme_id = str(detail.get("aweme_id", ""))
        desc = detail.get("desc", "") or "douyin_video"
        video_data = detail.get("video", {})

        # Duration in seconds (Douyin API usually provides milliseconds)
        raw_duration = video_data.get("duration", 0)
        duration_sec = raw_duration / 1000.0 if raw_duration > 100 else float(raw_duration)

        if enforce_duration and not (8.0 <= duration_sec <= 60.0):
            raise DurationOutOfRangeError(
                f"Video {aweme_id} duration {duration_sec:.1f}s outside accepted range [8.0s, 60.0s]"
            )

        # Select highest quality stream
        bitrates = video_data.get("bit_rate") or []
        candidates: List[Tuple[int, str]] = []

        if isinstance(bitrates, list) and bitrates:
            for item in bitrates:
                br = item.get("bit_rate", 0)
                urls = item.get("play_addr", {}).get("url_list", [])
                for u in urls:
                    candidates.append((br, u))

        # Fallback to play_addr or download_addr
        play_urls = video_data.get("play_addr", {}).get("url_list", [])
        for u in play_urls:
            candidates.append((1000, u))

        download_urls = video_data.get("download_addr", {}).get("url_list", [])
        for u in download_urls:
            candidates.append((500, u))

        if not candidates:
            raise VideoNotFoundError(f"No playable video URLs found for {aweme_id}")

        # Sort by bitrate descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        chosen_bitrate, chosen_url = candidates[0]

        # Key watermark stripping logic: replace /playwm/ with /play/
        clean_url = chosen_url.replace("/playwm/", "/play/")

        width = video_data.get("width", 0)
        height = video_data.get("height", 0)

        # Cover image
        cover_list = video_data.get("cover", {}).get("url_list", [])
        cover_url = cover_list[0] if cover_list else ""

        return CleanVideoInfo(
            aweme_id=aweme_id,
            title=desc,
            clean_url=clean_url,
            duration_sec=duration_sec,
            width=width,
            height=height,
            bitrate=chosen_bitrate,
            cover_url=cover_url,
            raw_payload=detail,
        )

    def download_video(
        self,
        clean_url: str,
        output_path: Path,
        apply_jitter: bool = True,
    ) -> Path:
        """
        Download video stream safely to disk with Jitter delay and retry management.

        Args:
            clean_url: Direct MP4 streaming URL.
            output_path: Target file destination Path.
            apply_jitter: Whether to execute anti-ban jitter delay (1.5s - 4.0s).

        Returns:
            Path of the saved MP4 file.
        """
        if apply_jitter:
            j_min = max(1.5, self.config.sourcing.jitter_min_sec)
            j_max = max(j_min, self.config.sourcing.jitter_max_sec)
            jitter_delay = random.uniform(j_min, j_max)
            logger.debug(f"Applying jitter delay: {jitter_delay:.2f}s")
            time.sleep(jitter_delay)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        max_retries = self.config.sourcing.max_retries

        for attempt in range(max_retries):
            try:
                with self._get_client() as client:
                    with client.stream("GET", clean_url) as resp:
                        if resp.status_code == 429:
                            if attempt < max_retries - 1:
                                time.sleep(2.0 * (attempt + 1))
                                continue
                            raise RateLimitError("Rate limited downloading video stream")

                        resp.raise_for_status()
                        with open(output_path, "wb") as f:
                            for chunk in resp.iter_bytes(chunk_size=65536):
                                f.write(chunk)

                if output_path.exists() and output_path.stat().st_size > 1024:
                    return output_path
                raise DouyinExtractorError(f"Downloaded file empty or too small: {output_path}")

            except httpx.HTTPError as e:
                if attempt < max_retries - 1:
                    time.sleep(1.0 + attempt)
                    continue
                raise DouyinExtractorError(f"Failed to stream video {clean_url}: {e}") from e

        return output_path

    def extract_and_download(
        self,
        url_or_text: str,
        output_dir: Optional[Path] = None,
        enforce_duration: bool = True,
        apply_jitter: bool = True,
    ) -> CleanVideoInfo:
        """
        Full end-to-end pipeline: parse link -> resolve ID -> fetch detail ->
        strip watermark -> validate duration -> download to cache/raw_footage/.
        """
        aweme_id = self.resolve_aweme_id(url_or_text)
        detail_json = self.fetch_video_detail(aweme_id)
        video_info = self.extract_clean_video_url(detail_json, enforce_duration=enforce_duration)

        dest_dir = output_dir or self.config.paths.cache_raw_footage_dir
        target_file = dest_dir / f"douyin_{aweme_id}.mp4"

        downloaded_path = self.download_video(
            clean_url=video_info.clean_url,
            output_path=target_file,
            apply_jitter=apply_jitter,
        )
        video_info.downloaded_path = downloaded_path
        return video_info
