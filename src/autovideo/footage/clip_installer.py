"""
Local CLIP model installer (ADR-020).

CLIP runs fully on this machine through onnxruntime (no torch / torchvision needed),
so installing it never touches the user's existing torch build.

Install steps:
1. Ensure Python deps (onnxruntime, tokenizers, huggingface_hub) - pip-installs only the missing ones.
2. Download the quantized ONNX CLIP ViT-B/32 (vision + text + tokenizer, ~155 MB) into bin/models/clip/.

Progress is exposed through a thread-safe status dict polled by the Settings UI.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from autovideo.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)

CLIP_REPO_ID = "Xenova/clip-vit-base-patch32"
CLIP_FILES: Dict[str, str] = {
    # local filename         : file inside the HF repo
    "vision_model.onnx": "onnx/vision_model_quantized.onnx",
    "text_model.onnx": "onnx/text_model_quantized.onnx",
    "tokenizer.json": "tokenizer.json",
    "preprocessor_config.json": "preprocessor_config.json",
}
REQUIRED_PACKAGES: Dict[str, str] = {
    # import name : pip package
    "onnxruntime": "onnxruntime",
    "tokenizers": "tokenizers",
    "huggingface_hub": "huggingface_hub",
}
MANIFEST_NAME = "clip_manifest.json"


def clip_model_dir(config: Optional[AppConfig] = None) -> Path:
    cfg = config or get_config()
    return cfg.paths.bin_dir / "models" / "clip"


def missing_packages() -> List[str]:
    missing = []
    for mod, pkg in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    return missing


def missing_model_files(model_dir: Path) -> List[str]:
    return [name for name in CLIP_FILES if not (model_dir / name).exists() or (model_dir / name).stat().st_size == 0]


class ClipInstaller:
    """Singleton-style installer with background thread and pollable status."""

    _lock = threading.Lock()
    _thread: Optional[threading.Thread] = None
    _state: Dict[str, Any] = {"state": "idle", "progress": 0.0, "message": "", "error": None}

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or get_config()
        self.model_dir = clip_model_dir(self.config)

    # ------------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        pkgs = missing_packages()
        files = missing_model_files(self.model_dir)
        installed = not pkgs and not files
        with self._lock:
            st = dict(self._state)
        size_mb = 0.0
        if self.model_dir.exists():
            size_mb = round(sum(f.stat().st_size for f in self.model_dir.glob("*") if f.is_file()) / 1e6, 1)
        manifest = {}
        mf = self.model_dir / MANIFEST_NAME
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        return {
            "installed": installed,
            "is_available": installed,
            "version": f"CLIP ViT-B/32 ONNX int8 ({size_mb} MB)" if installed else None,
            "missing_packages": pkgs,
            "missing_files": files,
            "model_dir": str(self.model_dir),
            "repo_id": CLIP_REPO_ID,
            "installed_at": manifest.get("installed_at"),
            "install_state": st["state"],
            "progress": st["progress"],
            "message": st["message"],
            "error": st["error"],
        }

    def _set(self, **kw: Any) -> None:
        with self._lock:
            self._state.update(kw)

    # ----------------------------------------------------------------- install
    def start_install(self) -> Dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"started": False, "message": "Đang cài đặt CLIP..."}
            self._state.update({"state": "running", "progress": 0.0, "message": "Bắt đầu cài đặt CLIP", "error": None})
            ClipInstaller._thread = threading.Thread(target=self._install_safe, name="clip-installer", daemon=True)
            ClipInstaller._thread.start()
        return {"started": True, "message": "Đã bắt đầu tải & cài đặt CLIP"}

    def _install_safe(self) -> None:
        try:
            self.install()
            self._set(state="done", progress=100.0, message="CLIP đã sẵn sàng")
        except Exception as exc:
            logger.exception("CLIP install failed")
            self._set(state="error", error=str(exc), message=f"Lỗi cài đặt CLIP: {exc}")

    def install(self) -> None:
        """Blocking install (used by the background thread and by CLI/tests)."""
        pkgs = missing_packages()
        if pkgs:
            self._set(progress=5.0, message=f"Đang cài thư viện Python: {', '.join(pkgs)}")
            cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *pkgs]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if proc.returncode != 0:
                raise RuntimeError(f"pip install thất bại: {proc.stderr[-400:]}")
            importlib.invalidate_caches()
            still = missing_packages()
            if still:
                raise RuntimeError(f"Không import được sau khi cài: {still}")

        from huggingface_hub import hf_hub_download

        self.model_dir.mkdir(parents=True, exist_ok=True)
        todo = missing_model_files(self.model_dir)
        total = max(1, len(todo))
        for i, local_name in enumerate(todo):
            remote = CLIP_FILES[local_name]
            self._set(progress=10.0 + 85.0 * i / total, message=f"Đang tải {remote} ({i + 1}/{total})")
            tmp_dir = self.model_dir / ".download"
            path = hf_hub_download(repo_id=CLIP_REPO_ID, filename=remote, local_dir=str(tmp_dir))
            shutil.move(str(path), str(self.model_dir / local_name))
        shutil.rmtree(self.model_dir / ".download", ignore_errors=True)

        self._set(progress=97.0, message="Đang kiểm tra model CLIP")
        from autovideo.footage.clip_engine import ClipEngine
        engine = ClipEngine(self.model_dir)
        vec = engine.embed_texts(["a spotted hyena walking"])
        if vec.shape[-1] < 256:
            raise RuntimeError(f"Kích thước embedding bất thường: {vec.shape}")
        (self.model_dir / MANIFEST_NAME).write_text(json.dumps({
            "repo_id": CLIP_REPO_ID,
            "files": CLIP_FILES,
            "embedding_dim": int(vec.shape[-1]),
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
