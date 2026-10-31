"""
Bilibili video downloader wrapper.
Uses BBDown portable binary if available, with automatic fallback to yt-dlp.
Executes subprocesses safely without shell=True.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)

BVID_REGEX = re.compile(r"(BV[a-zA-Z0-9]{10})", re.IGNORECASE)
BILIBILI_URL_REGEX = re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]{10})", re.IGNORECASE)


class BilibiliDownloaderError(Exception):
    """Base exception for Bilibili downloader errors."""
    pass


@dataclass
class BilibiliVideoInfo:
    """Metadata for a downloaded Bilibili video."""

    bvid: str
    title: str
    downloaded_path: Path
    duration_sec: float
    source_tool: str  # "BBDown" or "yt-dlp"


class BilibiliDownloader:
    """
    Downloads Bilibili videos using BBDown binary if present,
    or falls back automatically to yt-dlp.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        binary_manager: Optional[BinaryManager] = None,
    ):
        self.config = config or get_config()
        self.bin_mgr = binary_manager or BinaryManager(config=self.config)

    @staticmethod
    def extract_bvid(text: str) -> Optional[str]:
        """Extract Bilibili BV ID from text or URL."""
        match = BVID_REGEX.search(text)
        if match:
            return match.group(1)
        return None

    def _download_via_bbdown(
        self,
        url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Attempt downloading via BBDown binary."""
        bbdown_info = self.bin_mgr.get_binary("BBDown")
        if not bbdown_info.is_available or not bbdown_info.path:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd: List[str] = [
            str(bbdown_info.path),
            url,
            "--work-dir",
            str(output_dir),
            "--video-only",
            "false",
        ]

        logger.info(f"Invoking BBDown: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if result.returncode == 0:
                # Find recently created mp4 in output_dir
                mp4_files = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
                if mp4_files:
                    return mp4_files[0]
            else:
                logger.warning(f"BBDown returned code {result.returncode}: {result.stderr}")
        except Exception as e:
            logger.warning(f"BBDown execution failed: {e}")

        return None

    def _download_via_ytdlp(
        self,
        url: str,
        output_dir: Path,
        bvid: str,
    ) -> Path:
        """Fallback download via yt-dlp."""
        import yt_dlp

        output_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(output_dir / f"bilibili_{bvid}.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        expected_path = output_dir / f"bilibili_{bvid}.mp4"
        if expected_path.exists():
            return expected_path

        # If extension differed
        candidates = list(output_dir.glob(f"bilibili_{bvid}.*"))
        if candidates:
            return candidates[0]

        raise BilibiliDownloaderError(f"yt-dlp failed to download Bilibili video: {url}")

    def download(
        self,
        url_or_bvid: str,
        output_dir: Optional[Path] = None,
    ) -> BilibiliVideoInfo:
        """
        Download Bilibili video using BBDown with yt-dlp fallback.
        """
        bvid = self.extract_bvid(url_or_bvid)
        if not bvid:
            raise BilibiliDownloaderError(f"Invalid Bilibili identifier or URL: {url_or_bvid}")

        target_url = f"https://www.bilibili.com/video/{bvid}"
        dest_dir = output_dir or self.config.paths.cache_raw_footage_dir

        # 1. Try BBDown
        downloaded_path = self._download_via_bbdown(target_url, dest_dir)
        source_tool = "BBDown"

        # 2. Fallback to yt-dlp
        if not downloaded_path or not downloaded_path.exists():
            logger.info("Falling back to yt-dlp for Bilibili download")
            downloaded_path = self._download_via_ytdlp(target_url, dest_dir, bvid)
            source_tool = "yt-dlp"

        return BilibiliVideoInfo(
            bvid=bvid,
            title=downloaded_path.stem,
            downloaded_path=downloaded_path,
            duration_sec=0.0,
            source_tool=source_tool,
        )
