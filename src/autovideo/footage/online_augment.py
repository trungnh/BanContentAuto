"""
Online library augmentation (ADR-022).

When the local footage library has nothing better for a scene, search YouTube for NEW videos,
download a few, add them to the library (catalog + CLIP index), so the scene can be re-picked.

Request discipline (see ADR-020 / YouTube anti-bot):
- flat search only (1 request per query), at most `max_new` downloads per scene,
- videos already in the library / flagged inauthentic / about a look-alike species are skipped,
- the first YouTubeBlockedError stops everything and is reported (never retried in a loop).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from autovideo.footage.library import CatalogEntry, FootageLibrary
from autovideo.sourcing.relevance import anchor_matches
from autovideo.sourcing.universal import DEFAULT_NEGATIVE_TERMS, UniversalDownloader, YouTubeBlockedError

logger = logging.getLogger(__name__)


@dataclass
class AugmentResult:
    queries: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)       # video_ids added to the library
    skipped: int = 0
    blocked: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"queries": self.queries, "added": self.added, "skipped": self.skipped,
                "blocked": self.blocked, "errors": self.errors[:5]}


def _title_ok(title: str, anchor: str, confusers: Sequence[str]) -> bool:
    low = (title or "").lower()
    if not anchor_matches(low, anchor):
        return False
    anchor_low = (anchor or "").lower()
    if anchor_low and anchor_low not in low and any(c.lower() in low for c in confusers or []):
        return False
    for neg in DEFAULT_NEGATIVE_TERMS:
        n = neg.lower().strip()
        if n and n in low and n not in anchor_low:
            return False
    return True


def search_and_add(
    library: FootageLibrary,
    queries: Sequence[str],
    subject_anchor: str,
    confusers: Optional[Sequence[str]] = None,
    downloader: Optional[UniversalDownloader] = None,
    max_new: int = 3,
    per_query: int = 8,
    min_duration: float = 15.0,
    max_duration: float = 900.0,
    progress: Optional[Any] = None,
) -> AugmentResult:
    """Flat-search each query, download up to `max_new` new suitable videos, index them into the library."""
    dl = downloader or UniversalDownloader(library.config)
    res = AugmentResult(queries=[q for q in queries if q and q.strip()])
    known = set(library.videos)
    try:
        known |= set(library.load_catalog())
    except Exception:
        pass
    seen: set = set()
    for q in res.queries:
        if len(res.added) >= max_new:
            break
        try:
            info = dl.get_video_info(f"ytsearch{per_query}:{q}")
        except YouTubeBlockedError as exc:
            res.blocked = True
            res.errors.append(str(exc)[:200])
            break
        except Exception as exc:
            res.errors.append(f"search '{q}': {str(exc)[:150]}")
            continue
        for e in [x for x in (info.get("entries") or []) if isinstance(x, dict)]:
            if len(res.added) >= max_new:
                break
            vid = str(e.get("id") or "")
            if not vid or vid in known or vid in seen:
                continue
            seen.add(vid)
            dur = float(e.get("duration") or 0.0)
            title = str(e.get("title") or "")
            if not (min_duration <= dur <= max_duration) or not _title_ok(title, subject_anchor, confusers or []):
                res.skipped += 1
                continue
            url = str(e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}")
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={vid}"
            if progress:
                progress(f"Đang tải footage mới: {title[:60]}")
            try:
                path = dl._download_and_verify(url, vid, library.raw_dir)
            except YouTubeBlockedError as exc:
                res.blocked = True
                res.errors.append(str(exc)[:200])
                return res
            except Exception as exc:
                res.errors.append(f"download {vid}: {str(exc)[:150]}")
                continue
            entry = CatalogEntry(
                video_id=vid, path=path, title=title, description=str(e.get("description") or ""),
                uploader=str(e.get("channel") or e.get("uploader") or ""),
                webpage_url=f"https://www.youtube.com/watch?v={vid}", duration_sec=dur,
            )
            library.register(entry)
            if library.index_video(entry) is None:
                res.skipped += 1
                continue
            res.added.append(vid)
            known.add(vid)
            logger.info("Online augment: thêm '%s' (%s, %.0fs) vào thư viện", title[:60], vid, dur)
    return res
