"""
Shared footage relevance rules (ADR-019).

Single source of truth for:
- Subject anchor matching (used by BOTH query building in the coordinator and
  candidate scoring in UniversalDownloader, so the two can never disagree again).
- Scene-term extraction & matching (a candidate must mention at least one
  scene-specific visual term besides the subject anchor).
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

# Generic words that carry no scene-specific visual meaning for search matching.
_STOPWORDS = {
    "the", "and", "with", "from", "into", "onto", "over", "under", "near", "for", "its", "their",
    "this", "that", "these", "those", "of", "on", "in", "at", "to", "a", "an", "by", "as", "is",
    "shot", "shots", "close", "closeup", "up", "macro", "wide", "medium", "detail", "cinematic",
    "footage", "video", "videos", "clip", "clips", "documentary", "4k", "hd", "slow", "motion",
    "camera", "view", "angle", "lens", "lighting", "light", "dynamic", "telephoto", "extreme",
    "showing", "visible", "highlighting", "featuring", "very", "real", "wild", "wildlife",
    "animal", "animals", "nature", "behavior", "behaviour", "scene", "rotation", "glowing",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def anchor_head(subject_anchor: Optional[str]) -> str:
    """Return the head noun of an anchor ('spotted hyena' -> 'hyena')."""
    words = [w for w in _words(subject_anchor or "") if len(w) > 2]
    return words[-1] if words else ""


def _contains_word(text_words: Sequence[str], term: str) -> bool:
    """Whole-word match tolerant to simple plural/suffix forms ('hyena' ~ 'hyenas', 'hunt' ~ 'hunting')."""
    if not term:
        return False
    for w in text_words:
        if w == term:
            return True
        if len(term) >= 4 and w.startswith(term) and len(w) - len(term) <= 3:
            return True
        if len(w) >= 4 and term.startswith(w) and len(term) - len(w) <= 1:
            return True
    return False


def anchor_matches(text: str, subject_anchor: Optional[str]) -> bool:
    """
    True if text refers to the subject anchor: the full anchor phrase is present,
    or its head noun is present as a whole word. Modifier words alone ('spotted')
    never count.
    """
    if not subject_anchor:
        return True
    low = (text or "").lower()
    if subject_anchor.lower().strip() in low:
        return True
    return _contains_word(_words(low), anchor_head(subject_anchor))


def extract_scene_terms(
    keywords_en: Iterable[str],
    visual_prompt: Optional[str] = None,
    subject_anchor: Optional[str] = None,
    max_terms: int = 24,
) -> List[str]:
    """Collect distinctive scene terms (excluding anchor words and generic stopwords)."""
    anchor_words = set(_words(subject_anchor or ""))
    terms: List[str] = []
    sources = list(keywords_en or []) + ([visual_prompt] if visual_prompt else [])
    for src in sources:
        for w in _words(str(src)):
            if len(w) < 3 or w in _STOPWORDS or w in anchor_words or w.isdigit():
                continue
            if w not in terms:
                terms.append(w)
    return terms[:max_terms]


def matched_scene_terms(text: str, scene_terms: Sequence[str]) -> List[str]:
    """Return the scene terms present in text (whole-word, suffix tolerant)."""
    text_words = _words(text)
    return [t for t in scene_terms if _contains_word(text_words, t)]
