"""
Automated Binary Downloader and Setup Manager for BanContentAuto.
Ensures portable executables (ffmpeg, ffprobe, yt-dlp, BBDown) exist in bin/ directory
by first copying any available executables from system PATH/WinGet,
or automatically downloading them from official standalone GitHub releases.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from autovideo.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)

# Official Download Endpoints (Windows x64)
YTDLP_RELEASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
BBDOWN_RELEASE_URL = "https://github.com/nilaoda/BBDown/releases/download/1.6.3/BBDown_1.6.3_20240814_win-x64.zip"
BBDOWN_GITHUB_API = "https://api.github.com/repos/nilaoda/BBDown/releases/latest"
FFMPEG_ZIP_URL = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


@dataclass
class SetupResult:
    """Status result for a binary setup operation."""
    name: str
    installed: bool
    path: Optional[str]
    action: str  # "already_present" | "copied_from_system" | "downloaded" | "failed"
    message: str


class BinaryDownloader:
    """Discovers and downloads missing binaries into local bin/ directory."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.bin_dir = self.config.paths.bin_dir
        self.bin_dir.mkdir(parents=True, exist_ok=True)

    def _download_file(self, url: str, target_path: Path, progress_cb: Optional[Callable[[str], None]] = None) -> bool:
        """Download remote URL directly to a local file with browser User-Agent."""
        try:
            if progress_cb:
                progress_cb(f"Dang tai {target_path.name} tu {url}...")
            req = urllib.request.Request(url, headers={"User-Agent": "BanContentAuto-Setup/2.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                content = resp.read()
                target_path.write_bytes(content)
            # Make executable
            os.chmod(target_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            return True
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            if progress_cb:
                progress_cb(f"Loi khi tai {target_path.name}: {e}")
            return False

    def setup_ffmpeg_and_ffprobe(self, progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[SetupResult, SetupResult]:
        """Ensures ffmpeg.exe and ffprobe.exe exist in bin/."""
        ffmpeg_exe = self.bin_dir / "ffmpeg.exe"
        ffprobe_exe = self.bin_dir / "ffprobe.exe"

        ffmpeg_res = SetupResult(name="ffmpeg", installed=False, path=None, action="failed", message="")
        ffprobe_res = SetupResult(name="ffprobe", installed=False, path=None, action="failed", message="")

        # 1. Check if already present in bin/
        if ffmpeg_exe.is_file() and ffprobe_exe.is_file():
            ffmpeg_res = SetupResult("ffmpeg", True, str(ffmpeg_exe), "already_present", "Da co san trong bin/")
            ffprobe_res = SetupResult("ffprobe", True, str(ffprobe_exe), "already_present", "Da co san trong bin/")
            return ffmpeg_res, ffprobe_res

        # 2. Check if available in system PATH (e.g. WinGet / Gyan / Chocolatey)
        sys_ffmpeg = shutil.which("ffmpeg")
        sys_ffprobe = shutil.which("ffprobe")

        if sys_ffmpeg and not ffmpeg_exe.is_file():
            try:
                shutil.copy2(sys_ffmpeg, ffmpeg_exe)
                ffmpeg_res = SetupResult("ffmpeg", True, str(ffmpeg_exe), "copied_from_system", f"Da sao chep tu {sys_ffmpeg}")
            except Exception as e:
                logger.warning(f"Failed to copy system ffmpeg: {e}")

        if sys_ffprobe and not ffprobe_exe.is_file():
            try:
                shutil.copy2(sys_ffprobe, ffprobe_exe)
                ffprobe_res = SetupResult("ffprobe", True, str(ffprobe_exe), "copied_from_system", f"Da sao chep tu {sys_ffprobe}")
            except Exception as e:
                logger.warning(f"Failed to copy system ffprobe: {e}")

        if ffmpeg_exe.is_file() and ffprobe_exe.is_file():
            return ffmpeg_res, ffprobe_res

        # 3. If still missing, download portable FFmpeg zip and extract
        if not (ffmpeg_exe.is_file() and ffprobe_exe.is_file()):
            try:
                if progress_cb:
                    progress_cb("Dang tai goi FFmpeg Essentials Portable...")
                req = urllib.request.Request(FFMPEG_ZIP_URL, headers={"User-Agent": "BanContentAuto-Setup/2.0"})
                with urllib.request.urlopen(req, timeout=180) as resp:
                    zip_data = io.BytesIO(resp.read())
                    with zipfile.ZipFile(zip_data) as z:
                        for filename in z.namelist():
                            if filename.endswith("ffmpeg.exe") and not ffmpeg_exe.is_file():
                                ffmpeg_exe.write_bytes(z.read(filename))
                                ffmpeg_res = SetupResult("ffmpeg", True, str(ffmpeg_exe), "downloaded", "Da tai ve bin/")
                            elif filename.endswith("ffprobe.exe") and not ffprobe_exe.is_file():
                                ffprobe_exe.write_bytes(z.read(filename))
                                ffprobe_res = SetupResult("ffprobe", True, str(ffprobe_exe), "downloaded", "Da tai ve bin/")
            except Exception as e:
                logger.error(f"FFmpeg download failed: {e}")
                if not ffmpeg_exe.is_file():
                    ffmpeg_res = SetupResult("ffmpeg", False, None, "failed", f"Loi tai: {e}")
                if not ffprobe_exe.is_file():
                    ffprobe_res = SetupResult("ffprobe", False, None, "failed", f"Loi tai: {e}")

        return ffmpeg_res, ffprobe_res

    def setup_ytdlp(self, progress_cb: Optional[Callable[[str], None]] = None) -> SetupResult:
        """Ensures yt-dlp.exe exists in bin/."""
        ytdlp_exe = self.bin_dir / "yt-dlp.exe"

        # 1. Already in bin/
        if ytdlp_exe.is_file():
            return SetupResult("yt-dlp", True, str(ytdlp_exe), "already_present", "Da co san trong bin/")

        # 2. Check system PATH (e.g. pip installed)
        sys_ytdlp = shutil.which("yt-dlp")
        if sys_ytdlp:
            try:
                shutil.copy2(sys_ytdlp, ytdlp_exe)
                return SetupResult("yt-dlp", True, str(ytdlp_exe), "copied_from_system", f"Da sao chep tu {sys_ytdlp}")
            except Exception as e:
                logger.warning(f"Could not copy yt-dlp: {e}")

        # 3. Download standalone yt-dlp.exe
        ok = self._download_file(YTDLP_RELEASE_URL, ytdlp_exe, progress_cb)
        if ok:
            return SetupResult("yt-dlp", True, str(ytdlp_exe), "downloaded", "Da tai thanh cong yt-dlp.exe vao bin/")
        return SetupResult("yt-dlp", False, None, "failed", "Khong the tai yt-dlp.exe")

    def setup_bbdown(self, progress_cb: Optional[Callable[[str], None]] = None) -> SetupResult:
        """Ensures BBDown.exe exists in bin/ for Bilibili high-resolution downloads."""
        bbdown_exe = self.bin_dir / "BBDown.exe"

        # 1. Already present in bin/
        if bbdown_exe.is_file():
            return SetupResult("BBDown", True, str(bbdown_exe), "already_present", "Da co san trong bin/")

        # 2. Check system PATH
        sys_bbdown = shutil.which("BBDown")
        if sys_bbdown:
            try:
                shutil.copy2(sys_bbdown, bbdown_exe)
                return SetupResult("BBDown", True, str(bbdown_exe), "copied_from_system", f"Da sao chep tu {sys_bbdown}")
            except Exception as e:
                logger.warning(f"Could not copy BBDown: {e}")

        # 3. Find latest GitHub release asset
        download_url = BBDOWN_RELEASE_URL
        try:
            req = urllib.request.Request(BBDOWN_GITHUB_API, headers={"User-Agent": "BanContentAuto-Setup/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                rel_data = json.loads(resp.read().decode("utf-8"))
                for asset in rel_data.get("assets", []):
                    if "win-x64" in asset.get("name", "") and asset.get("name", "").endswith(".zip"):
                        download_url = asset["browser_download_url"]
                        break
        except Exception:
            pass  # Fall back to known release URL

        try:
            if progress_cb:
                progress_cb(f"Dang tai BBDown tu {download_url}...")
            req = urllib.request.Request(download_url, headers={"User-Agent": "BanContentAuto-Setup/2.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                zip_data = io.BytesIO(resp.read())
                with zipfile.ZipFile(zip_data) as z:
                    for filename in z.namelist():
                        if filename.lower().endswith("bbdown.exe"):
                            bbdown_exe.write_bytes(z.read(filename))
                            os.chmod(bbdown_exe, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                            return SetupResult("BBDown", True, str(bbdown_exe), "downloaded", "Da tai va giai nen BBDown.exe vao bin/")
        except Exception as e:
            logger.error(f"BBDown download failed: {e}")
            return SetupResult("BBDown", False, None, "failed", f"Loi tai BBDown: {e}")

        return SetupResult("BBDown", False, None, "failed", "Khong tim thay file BBDown.exe trong goi nen")

    def setup_all(self, progress_cb: Optional[Callable[[str], None]] = None) -> Dict[str, SetupResult]:
        """Executes setup for all 4 external binaries."""
        results = {}

        if progress_cb:
            progress_cb("Bat dau chuan bi cong cu trong thu muc bin/...")

        ffmpeg_res, ffprobe_res = self.setup_ffmpeg_and_ffprobe(progress_cb)
        results["ffmpeg"] = ffmpeg_res
        results["ffprobe"] = ffprobe_res

        ytdlp_res = self.setup_ytdlp(progress_cb)
        results["yt-dlp"] = ytdlp_res

        bbdown_res = self.setup_bbdown(progress_cb)
        results["BBDown"] = bbdown_res

        if progress_cb:
            progress_cb("Hoan tat quet va thiet lap toan bo cong cu ngoai vi!")

        return results
