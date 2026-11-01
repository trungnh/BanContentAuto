"""
Footage Library (ADR-020): local CLIP index over downloaded source videos.

- Catalog: every video in cache/raw_footage with known metadata (title/description/video_id),
  merged from previous projects' project_state.json and a persistent catalog.json.
- Index: frames sampled at `fps` -> CLIP image embeddings (float16), cached per file as .npz,
  plus shot-cut timestamps derived from embedding discontinuities.

No network calls and no LLM calls: indexing runs fully on the local CPU.
"""

from __future__ import annotations

import glob
import json
import logging
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.footage.clip_engine import ClipEngine

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass
class CatalogEntry:
    video_id: str
    path: Path
    title: str = ""
    description: str = ""
    uploader: str = ""
    webpage_url: str = ""
    duration_sec: float = 0.0
    inauthentic: bool = False   # judged AI-generated / CGI -> never used as documentary footage

    def text(self) -> str:
        return f"{self.title} {self.description} {self.uploader}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id, "path": str(self.path), "title": self.title,
            "description": self.description[:2000], "uploader": self.uploader,
            "webpage_url": self.webpage_url, "duration_sec": self.duration_sec,
            "inauthentic": self.inauthentic,
        }


@dataclass
class VideoIndex:
    entry: CatalogEntry
    times: np.ndarray            # (N,) seconds
    embeddings: np.ndarray       # (N, D) float32, L2-normalized
    cuts: List[float] = field(default_factory=list)
    duration_sec: float = 0.0


class FootageLibrary:
    """Catalog + CLIP index of local source footage."""

    def __init__(
        self,
        clip: ClipEngine,
        config: Optional[AppConfig] = None,
        fps: float = 1.0,
        max_frames_per_video: int = 900,
        cut_threshold: float = 0.80,
    ) -> None:
        self.clip = clip
        self.config = config or get_config()
        self.fps = fps
        self.max_frames = max_frames_per_video
        self.cut_threshold = cut_threshold
        self.raw_dir = self.config.paths.cache_raw_footage_dir
        self.index_dir = self.config.paths.cache_dir / "footage_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.index_dir / "catalog.json"
        bm = BinaryManager(self.config)
        self.ffmpeg, _ = bm.find_binary("ffmpeg")
        self.ffprobe, _ = bm.find_binary("ffprobe")
        self._lock = threading.Lock()
        self.videos: Dict[str, VideoIndex] = {}

    # ================================================================ catalog
    def load_catalog(self) -> Dict[str, CatalogEntry]:
        """Merge persistent catalog.json with metadata recorded in all project states."""
        cat: Dict[str, CatalogEntry] = {}
        if self.catalog_path.exists():
            try:
                for d in json.loads(self.catalog_path.read_text(encoding="utf-8")).values():
                    known = set(CatalogEntry.__dataclass_fields__)
                    e = CatalogEntry(**{**{k: v for k, v in d.items() if k in known}, "path": Path(d["path"])})
                    if e.path.exists():
                        cat[e.video_id] = e
            except Exception as exc:
                logger.warning("catalog.json hỏng, bỏ qua: %s", exc)

        renders = self.config.paths.renders_dir
        for sp in glob.glob(str(renders / "*" / "project_state.json")):
            try:
                st = json.loads(Path(sp).read_text(encoding="utf-8"))
            except Exception:
                continue
            for rec in st.get("completed_scenes") or []:
                m = rec.get("metadata") or {}
                fname, vid = m.get("raw_filename"), m.get("video_id")
                if not fname or not vid or vid in cat:
                    continue
                p = self.raw_dir / fname
                if p.exists():
                    cat[vid] = CatalogEntry(
                        video_id=str(vid), path=p, title=str(m.get("title") or ""),
                        description=str(m.get("description") or ""), uploader=str(m.get("uploader") or ""),
                        webpage_url=str(m.get("webpage_url") or ""),
                    )
        return cat

    def register(self, entry: CatalogEntry) -> None:
        """Persist a newly downloaded video into catalog.json."""
        with self._lock:
            data: Dict[str, Any] = {}
            if self.catalog_path.exists():
                try:
                    data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data[entry.video_id] = entry.to_dict()
            self.catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def flag_inauthentic(self, video_id: str) -> None:
        """Mark a video as AI-generated/CGI (persisted) so it is excluded now and in future projects."""
        vi = self.videos.get(video_id)
        if vi is None or vi.entry.inauthentic:
            return
        vi.entry.inauthentic = True
        logger.warning("Footage library: đánh dấu %s (%s) là AI-generated/CGI -> loại khỏi thư viện",
                       video_id, vi.entry.title[:60])
        self.register(vi.entry)

    # ================================================================== index
    def _probe(self, path: Path) -> tuple[int, int, float]:
        cmd = [str(self.ffprobe or "ffprobe"), "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, creationflags=_CREATE_NO_WINDOW)
        d = json.loads(r.stdout or "{}")
        s = (d.get("streams") or [{}])[0]
        return int(s.get("width") or 0), int(s.get("height") or 0), float((d.get("format") or {}).get("duration") or 0.0)

    def _decode_frames(self, path: Path, width: int, height: int, duration: float) -> tuple[np.ndarray, List[np.ndarray]]:
        fps = self.fps
        if duration * fps > self.max_frames:
            fps = self.max_frames / max(duration, 1.0)
        out_h = 224
        out_w = max(224, int(round(out_h * (width / max(height, 1)) / 2) * 2))
        cmd = [str(self.ffmpeg or "ffmpeg"), "-v", "error", "-i", str(path),
               "-vf", f"fps={fps:.4f},scale={out_w}:{out_h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=max(120, duration * 2), creationflags=_CREATE_NO_WINDOW)
        frame_bytes = out_w * out_h * 3
        n = len(r.stdout) // frame_bytes
        buf = np.frombuffer(r.stdout[: n * frame_bytes], dtype=np.uint8).reshape(n, out_h, out_w, 3)
        times = (np.arange(n, dtype=np.float32) + 0.5) / fps
        return times, [buf[i] for i in range(n)]

    def _cache_file(self, entry: CatalogEntry) -> Path:
        st = entry.path.stat()
        return self.index_dir / f"{entry.video_id}_{int(st.st_size)}_{int(self.fps * 100)}_v{INDEX_VERSION}.npz"

    def index_video(self, entry: CatalogEntry) -> Optional[VideoIndex]:
        if entry.video_id in self.videos:
            return self.videos[entry.video_id]
        cache = self._cache_file(entry)
        try:
            if cache.exists():
                z = np.load(cache)
                vi = VideoIndex(entry, z["times"], z["emb"].astype(np.float32), list(z["cuts"]), float(z["duration"]))
            else:
                w, h, dur = self._probe(entry.path)
                if w <= 0 or h <= 0 or dur <= 0:
                    return None
                if w < h:
                    logger.info("Footage library: bỏ qua video dọc %s (%dx%d)", entry.path.name, w, h)
                    return None
                times, frames = self._decode_frames(entry.path, w, h, dur)
                if len(frames) < 3:
                    return None
                emb = self.clip.embed_images(frames)
                sims = np.sum(emb[1:] * emb[:-1], axis=1)
                cuts = [float((times[i] + times[i + 1]) / 2) for i in np.where(sims < self.cut_threshold)[0]]
                np.savez_compressed(cache, times=times, emb=emb.astype(np.float16), cuts=np.array(cuts, dtype=np.float32),
                                    duration=np.float32(dur))
                vi = VideoIndex(entry, times, emb, cuts, dur)
            entry.duration_sec = vi.duration_sec
            self.videos[entry.video_id] = vi
            return vi
        except Exception as exc:
            logger.warning("Không index được %s: %s", entry.path.name, exc)
            return None

    def build(
        self,
        entries: Iterable[CatalogEntry],
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> int:
        entries = list(entries)
        ok = 0
        for i, e in enumerate(entries, start=1):
            if self.index_video(e) is not None:
                ok += 1
            if progress:
                progress(i, len(entries), e.title or e.video_id)
        return ok
