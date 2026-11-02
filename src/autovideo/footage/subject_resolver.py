"""
Subject resolution (ADR-023, F1).

Turns a (usually Vietnamese) topic into the precise English visual subject used everywhere in
footage sourcing: library filtering, CLIP subject checks, online search queries and the judge.

Order: cached result -> ONE LLM call (anchor + aliases + look-alike confusers) -> hardcoded map.
A generic niche default (e.g. 'wildlife animal') is never accepted from the LLM, and is flagged
when it is the only thing the fallback map can produce, so the problem is visible instead of
silently matching every animal video in the library.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

GENERIC_ANCHORS = {
    "wildlife animal", "historical ancient", "extreme weather disaster", "military history battlefield",
    "documentary", "animal", "wildlife", "nature",
}

_lock = threading.Lock()


def build_prompt(topic: str, skill_id: str) -> str:
    return (
        "You prepare stock-footage searches for a documentary video.\n"
        f"Video topic (may be Vietnamese): {topic}\n"
        f"Niche: {skill_id}\n\n"
        "Identify the ONE main visual subject that must appear on screen (a specific animal species, "
        "place, event, object or person). Give its precise common English name as used in YouTube titles "
        "(2-4 words, e.g. 'sperm whale', 'honey badger', 'Angkor Wat', 'Hongwu Emperor').\n"
        "Also list up to 4 alternative names/spellings (aliases) and up to 5 visually similar subjects "
        "that a footage search could confuse with it (confusers).\n"
        'Return ONLY JSON: {"anchor": "...", "aliases": ["..."], "confusers": ["..."]}'
    )


def parse_response(raw: str) -> Dict[str, Any]:
    import re
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise ValueError(f"no JSON in subject response: {raw[:150]!r}")
    data = json.loads(m.group(0))
    anchor = str(data.get("anchor") or "").strip().strip('"').lower()
    if not anchor or anchor in GENERIC_ANCHORS or len(anchor) > 60:
        raise ValueError(f"unusable anchor {anchor!r}")
    aliases = [str(a).strip().lower() for a in (data.get("aliases") or []) if str(a).strip()][:4]
    confusers = [str(c).strip() for c in (data.get("confusers") or []) if str(c).strip()]
    confusers = [c for c in confusers if c.lower() != anchor and c.lower() not in aliases][:5]
    return {"anchor": anchor, "aliases": aliases, "confusers": confusers}


class SubjectResolver:
    def __init__(self, cache_path: Path, llm_call: Optional[Callable[[str], str]] = None,
                 fallback: Optional[Callable[[str, str], str]] = None) -> None:
        self.cache_path = Path(cache_path)
        self.llm_call = llm_call
        self.fallback = fallback

    @staticmethod
    def key(topic: str, skill_id: str) -> str:
        return f"{skill_id}|{(topic or '').strip()}"

    def _load(self) -> Dict[str, Any]:
        try:
            if self.cache_path.exists():
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self, key: str, value: Dict[str, Any]) -> None:
        with _lock:
            data = self._load()
            data[key] = value
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def resolve(self, topic: str, skill_id: str, use_cache: bool = True) -> Dict[str, Any]:
        key = self.key(topic, skill_id)
        if use_cache:
            cached = self._load().get(key)
            if cached and cached.get("anchor") and cached.get("source") == "llm":
                return cached
        if self.llm_call is not None:
            try:
                res = parse_response(self.llm_call(build_prompt(topic, skill_id)))
                res["source"] = "llm"
                self._save(key, res)
                logger.info("Subject resolver: '%s' -> '%s' (aliases=%s, confusers=%s)",
                            topic[:60], res["anchor"], res["aliases"], res["confusers"])
                return res
            except Exception as exc:
                logger.warning("Subject resolver LLM thất bại (%s) — dùng bảng ánh xạ dự phòng", exc)
        anchor = (self.fallback(topic, skill_id) if self.fallback else "") or ""
        res = {"anchor": anchor, "aliases": [], "confusers": [], "source": "map",
               "generic": anchor.lower() in GENERIC_ANCHORS}
        if res["generic"]:
            logger.warning("Subject resolver: chủ đề '%s' chỉ ra anchor chung chung '%s' — footage có thể lạc đề",
                           topic[:60], anchor)
        return res
