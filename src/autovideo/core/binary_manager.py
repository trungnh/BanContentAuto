"""
External binary manager for BanContentAuto.
Discovers, validates, and probes versions of portable binaries (ffmpeg, ffprobe, BBDown, yt-dlp)
with priority given to local bin/ directory before falling back to system PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from autovideo.core.config import AppConfig, get_config


class BinaryNotFoundError(FileNotFoundError):
    """Raised when a required external binary is missing from both bin/ and PATH."""

    def __init__(self, binary_name: str, search_path: Path):
        self.binary_name = binary_name
        self.search_path = search_path
        super().__init__(
            f"Required binary '{binary_name}' was not found in local bin directory ({search_path}) "
            f"or system PATH. Please place '{binary_name}.exe' in '{search_path}' or install it in PATH."
        )


@dataclass
class BinaryInfo:
    """Metadata regarding an external binary executable."""

    name: str
    path: Optional[Path]
    is_available: bool
    version: Optional[str]
    source: str  # "bin", "system", or "missing"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "is_available": self.is_available,
            "available": self.is_available,
            "version": self.version,
            "source": self.source,
        }


class BinaryManager:
    """
    Manages detection and validation of external binaries.
    Gives priority to local bin/ folder, then system PATH.
    """

    KNOWN_BINARIES = ("ffmpeg", "ffprobe", "BBDown", "yt-dlp")

    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config or get_config()

    @property
    def bin_dir(self) -> Path:
        return self._config.paths.bin_dir

    def _resolve_executable_name(self, name: str) -> List[str]:
        """Return potential filename variations for the current OS."""
        candidates = [name]
        if sys.platform == "win32":
            if not name.lower().endswith((".exe", ".cmd", ".bat")):
                candidates.insert(0, f"{name}.exe")
                candidates.append(f"{name}.cmd")
                candidates.append(f"{name}.bat")
        return candidates

    def find_binary(self, name: str) -> tuple[Optional[Path], str]:
        """
        Locate the binary executable.
        Returns: (path, source) where source is 'bin', 'system', or 'missing'.
        """
        candidates = self._resolve_executable_name(name)

        # 1. Search in local bin_dir first
        if self.bin_dir.exists():
            for candidate in candidates:
                local_path = self.bin_dir / candidate
                if local_path.is_file() and os.access(str(local_path), os.X_OK):
                    return local_path.resolve(), "bin"
                # On Windows, is_file is sufficient even if X_OK isn't strictly set
                if sys.platform == "win32" and local_path.is_file():
                    return local_path.resolve(), "bin"

        # 2. Fall back to system PATH
        for candidate in candidates:
            system_path = shutil.which(candidate)
            if system_path:
                return Path(system_path).resolve(), "system"

        return None, "missing"

    def _extract_version_from_output(self, name: str, output: str) -> Optional[str]:
        """Parse version string from binary stdout/stderr output."""
        name_lower = name.lower()

        if "ffmpeg" in name_lower or "ffprobe" in name_lower:
            match = re.search(r"(?:ffmpeg|ffprobe)\s+version\s+([^\s,]+)", output, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        if "yt-dlp" in name_lower:
            # yt-dlp outputs just the version like '2024.08.06'
            match = re.search(r"(\d{4}\.\d{2}\.\d{2}(?:\.\d+)?)", output)
            if match:
                return match.group(1).strip()

        if "bbdown" in name_lower:
            match = re.search(r"BBDown\s*(?:v|version)?\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)", output, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Generic fallback: search for standard semver pattern
        match = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", output)
        if match:
            return match.group(1).strip()

        first_line = output.strip().splitlines()
        return first_line[0][:50] if first_line else "unknown"

    def probe_version(self, path: Path, name: str, timeout_sec: float = 3.0) -> Optional[str]:
        """Safely invoke binary to determine its version."""
        flags_to_try = [["--version"], ["--help"], ["-version"], ["-v"], ["-h"]]
        for flags in flags_to_try:
            try:
                proc = subprocess.run(
                    [str(path)] + flags,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout_sec,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                output = (proc.stdout or "") + " " + (proc.stderr or "")
                if output.strip():
                    version = self._extract_version_from_output(name, output)
                    if version and not any(bad in version.lower() for bad in ("missing", "usage", "argument", "error")):
                        return version
            except (subprocess.SubprocessError, OSError):
                continue
        return "unknown"

    def check_binary(self, name: str) -> BinaryInfo:
        """Inspect and return readiness of a specific binary."""
        path, source = self.find_binary(name)
        if not path:
            return BinaryInfo(
                name=name,
                path=None,
                is_available=False,
                version=None,
                source="missing",
            )

        version = self.probe_version(path, name)
        return BinaryInfo(
            name=name,
            path=path,
            is_available=True,
            version=version,
            source=source,
        )

    def check_all(self, extra_binaries: Optional[List[str]] = None) -> Dict[str, BinaryInfo]:
        """Check status of all known and specified extra binaries."""
        binaries = list(self.KNOWN_BINARIES)
        if extra_binaries:
            for b in extra_binaries:
                if b not in binaries:
                    binaries.append(b)

        return {name: self.check_binary(name) for name in binaries}

    def require(self, name: str) -> BinaryInfo:
        """
        Require that a binary is available.
        Raises BinaryNotFoundError if missing.
        """
        info = self.check_binary(name)
        if not info.is_available:
            raise BinaryNotFoundError(binary_name=name, search_path=self.bin_dir)
        return info

    def get_binary_path(self, name: str) -> Path:
        """Returns the resolved executable Path for the given binary name."""
        info = self.require(name)
        if not info.path:
            raise BinaryNotFoundError(binary_name=name, search_path=self.bin_dir)
        return info.path

    def is_ready(self, required: tuple[str, ...] = ("ffmpeg", "ffprobe")) -> bool:
        """Return True if all essential required binaries are present and executable."""
        for name in required:
            info = self.check_binary(name)
            if not info.is_available:
                return False
        return True
