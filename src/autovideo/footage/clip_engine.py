"""
CLIP ViT-B/32 inference on onnxruntime (ADR-020) - no torch dependency.

- embed_images(list of BGR np.ndarray) -> (N, D) L2-normalized
- embed_texts(list of str)             -> (N, D) L2-normalized
Cosine similarity = dot product of the normalized vectors.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
_CTX_LEN = 77


class ClipUnavailableError(RuntimeError):
    """CLIP model or runtime not installed."""


def _l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.maximum(n, 1e-8)


class ClipEngine:
    _instances: dict = {}
    _instances_lock = threading.Lock()

    def __init__(self, model_dir: Path, threads: int = 0) -> None:
        self.model_dir = Path(model_dir)
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except Exception as exc:  # pragma: no cover - depends on env
            raise ClipUnavailableError(f"Thiếu thư viện CLIP runtime: {exc}") from exc

        vis, txt, tok = (self.model_dir / n for n in ("vision_model.onnx", "text_model.onnx", "tokenizer.json"))
        for p in (vis, txt, tok):
            if not p.exists():
                raise ClipUnavailableError(f"Chưa cài model CLIP (thiếu {p.name}). Vào Cài đặt → Binaries để tải.")

        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self._vision = ort.InferenceSession(str(vis), sess_options=opts, providers=["CPUExecutionProvider"])
        self._text = ort.InferenceSession(str(txt), sess_options=opts, providers=["CPUExecutionProvider"])
        self._tok = Tokenizer.from_file(str(tok))
        self._image_size = 224
        pp = self.model_dir / "preprocessor_config.json"
        if pp.exists():
            try:
                cfg = json.loads(pp.read_text(encoding="utf-8"))
                crop = cfg.get("crop_size")
                self._image_size = int(crop.get("height", 224) if isinstance(crop, dict) else (crop or 224))
            except Exception:
                pass
        self._vision_out = self._pick_output(self._vision, ("image_embeds",))
        self._text_out = self._pick_output(self._text, ("text_embeds",))
        self._text_inputs = {i.name for i in self._text.get_inputs()}
        self._lock = threading.Lock()

    @classmethod
    def shared(cls, model_dir: Path) -> "ClipEngine":
        key = str(Path(model_dir).resolve())
        with cls._instances_lock:
            if key not in cls._instances:
                cls._instances[key] = cls(Path(model_dir))
            return cls._instances[key]

    @staticmethod
    def _pick_output(sess, preferred: Sequence[str]) -> str:
        names = [o.name for o in sess.get_outputs()]
        for p in preferred:
            if p in names:
                return p
        return names[0]

    # ----------------------------------------------------------------- images
    def _preprocess(self, img_bgr: np.ndarray) -> np.ndarray:
        s = self._image_size
        h, w = img_bgr.shape[:2]
        scale = s / min(h, w)
        nh, nw = max(s, round(h * scale)), max(s, round(w * scale))
        img = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_CUBIC)
        y0, x0 = (nh - s) // 2, (nw - s) // 2
        img = img[y0:y0 + s, x0:x0 + s]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = (img - _MEAN) / _STD
        return img.transpose(2, 0, 1)

    def embed_images(self, images: List[np.ndarray], batch_size: int = 16) -> np.ndarray:
        if not images:
            return np.zeros((0, 512), dtype=np.float32)
        out = []
        for i in range(0, len(images), batch_size):
            batch = np.stack([self._preprocess(im) for im in images[i:i + batch_size]]).astype(np.float32)
            with self._lock:
                res = self._vision.run([self._vision_out], {"pixel_values": batch})[0]
            out.append(res)
        return _l2(np.concatenate(out, axis=0).astype(np.float32))

    # ------------------------------------------------------------------ texts
    def _tokenize(self, texts: List[str]) -> tuple[np.ndarray, np.ndarray]:
        ids = np.full((len(texts), _CTX_LEN), 49407, dtype=np.int64)  # <|endoftext|> as pad
        mask = np.zeros((len(texts), _CTX_LEN), dtype=np.int64)
        for row, t in enumerate(texts):
            enc = self._tok.encode(t or "")
            tok = enc.ids[:_CTX_LEN]
            if tok and tok[-1] != 49407:
                tok = tok[:_CTX_LEN - 1] + [49407]
            ids[row, :len(tok)] = tok
            mask[row, :len(tok)] = 1
        return ids, mask

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 512), dtype=np.float32)
        ids, mask = self._tokenize(list(texts))
        feeds = {"input_ids": ids}
        if "attention_mask" in self._text_inputs:
            feeds["attention_mask"] = mask
        with self._lock:
            res = self._text.run([self._text_out], feeds)[0]
        return _l2(res.astype(np.float32))


def load_clip_engine(model_dir: Optional[Path] = None) -> Optional[ClipEngine]:
    """Return a shared engine, or None (with a warning) if CLIP is not installed."""
    from autovideo.footage.clip_installer import clip_model_dir
    try:
        return ClipEngine.shared(model_dir or clip_model_dir())
    except ClipUnavailableError as exc:
        logger.warning("CLIP không khả dụng: %s", exc)
        return None
