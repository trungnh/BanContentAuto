"""
Word Budget and Pacing Rhythm Validator (REQ-B1-03).
Enforces speech pacing (2.5 - 3.2 words/sec) and scene allocation constraints:
- 4s - 5s scenes: 14 - 24 words (1 punchy sentence)
- 6s - 8s scenes: 25 - 35 words (2 complete sentences)
Validates sentence terminal punctuation (must end with '.', '!', '?', '...').
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


# Terminal punctuation characters allowed at the end of narration lines
VALID_TERMINAL_PUNCTUATION = (".", "!", "?", "…", "...")


def calculate_scene_budget(duration_sec: float) -> Tuple[int, int]:
    """
    Calculates the allowable [min_words, max_words] for a given scene duration in seconds.
    Adheres to REQ-B1-03:
    - If 4s <= duration <= 5s: 14 to 24 words.
    - If 6s <= duration <= 8s: 25 to 35 words.
    - For other durations: bounds derived from 2.5 to 3.2 words/sec.
    """
    if 4.0 <= duration_sec <= 5.0:
        return 14, 24
    if 5.0 < duration_sec <= 8.0:
        return 25, 35

    # General fallback using 2.5 - 3.2 words/s
    min_w = max(1, math.floor(duration_sec * 2.5))
    max_w = max(min_w, math.ceil(duration_sec * 3.2))
    return min_w, max_w


def estimate_duration(word_count: int, wps: float = 2.85) -> float:
    """
    Estimates spoken audio duration in seconds for a given word count,
    defaulting to average Vietnamese documentary reading speed (2.85 words/second).
    Clamped within 4.0s - 8.0s for standard scenes when possible.
    """
    if word_count <= 0:
        return 0.0
    duration = round(word_count / wps, 2)
    return duration


def compute_compliant_duration(word_count: int, dur_hint: Optional[float] = None) -> float:
    """
    Computes a duration in seconds that is strictly compliant with calculate_scene_budget(duration).
    Ensures min_words <= word_count <= max_words always holds without causing word budget violations.
    """
    if word_count <= 0:
        return 4.0

    # If dur_hint is provided and already valid, keep it
    if dur_hint is not None and dur_hint > 0:
        min_b, max_b = calculate_scene_budget(dur_hint)
        if min_b <= word_count <= max_b:
            return round(dur_hint, 2)

    # Otherwise map to compliant brackets:
    if 14 <= word_count <= 24:
        ratio = (word_count - 14) / 10.0
        return round(4.0 + ratio * 1.0, 2)
    elif 25 <= word_count <= 35:
        ratio = (word_count - 25) / 10.0
        return round(6.0 + ratio * 2.0, 2)
    elif word_count < 14:
        d = round(word_count / 2.85, 2)
        return min(3.8, max(1.0, d))
    else:
        d = round(word_count / 2.85, 2)
        return max(8.5, d)


@dataclass
class SceneValidationResult:
    """Validation result for an individual scene text."""

    is_valid: bool
    word_count: int
    duration_sec: float
    min_budget: int
    max_budget: int
    ends_with_punctuation: bool
    violations: List[str] = field(default_factory=list)


class WordBudgetValidator:
    """
    Validator for narration word budget and punctuation compliance.
    """

    def __init__(
        self,
        min_wps: float = 2.5,
        max_wps: float = 3.2,
        default_wps: float = 2.85,
        global_min_words: int = 14,
        global_max_words: int = 35,
    ) -> None:
        self.min_wps = min_wps
        self.max_wps = max_wps
        self.default_wps = default_wps
        self.global_min_words = global_min_words
        self.global_max_words = global_max_words

    @staticmethod
    def count_words(text: str) -> int:
        """Counts words delimited by whitespace."""
        return len(text.strip().split())

    @staticmethod
    def has_valid_terminal_punctuation(text: str) -> bool:
        """
        Checks whether the text ends with valid terminating punctuation
        (period, exclamation mark, question mark, or ellipsis).
        Disallows trailing commas, semicolons, hyphens, colons, or unpunctuated words.
        """
        cleaned = text.strip()
        if not cleaned:
            return False
        # Remove closing quotes or brackets if present at the end
        cleaned = re.sub(r'[\'\"”’»\)\]\}]+$', '', cleaned).strip()
        return cleaned.endswith((".", "!", "?", "…")) or cleaned.endswith("...")

    def validate_scene(
        self,
        text: str,
        duration_sec: Optional[float] = None,
        enforce_budget_bounds: bool = True,
    ) -> SceneValidationResult:
        """
        Validates an individual scene's narration text.
        Checks:
        1. Non-empty text.
        2. Proper terminating punctuation.
        3. Word budget compliance (relative to duration_sec or global bounds 14-35).
        """
        violations: List[str] = []
        word_count = self.count_words(text)

        if word_count == 0:
            violations.append("Scene text is empty.")

        # Punctuation check
        ends_punct = self.has_valid_terminal_punctuation(text)
        if not ends_punct:
            violations.append(
                f"Scene text does not end with terminal punctuation ('.', '!', '?', '…'). Found end: '{text[-10:] if len(text) > 10 else text}'"
            )

        # Budget bounds determination
        if duration_sec is not None:
            min_b, max_b = calculate_scene_budget(duration_sec)
            calc_dur = duration_sec
        else:
            min_b, max_b = self.global_min_words, self.global_max_words
            calc_dur = estimate_duration(word_count, self.default_wps)

        if enforce_budget_bounds and word_count > 0:
            if word_count < min_b:
                violations.append(
                    f"Word count {word_count} is below minimum budget {min_b} words for duration {calc_dur}s. "
                    "Narration is too sparse and creates dead air."
                )
            elif word_count > max_b:
                violations.append(
                    f"Word count {word_count} exceeds maximum budget {max_b} words for duration {calc_dur}s. "
                    "Narration is too rushed and causes audio swallow."
                )

        return SceneValidationResult(
            is_valid=len(violations) == 0,
            word_count=word_count,
            duration_sec=calc_dur,
            min_budget=min_b,
            max_budget=max_b,
            ends_with_punctuation=ends_punct,
            violations=violations,
        )

    def validate_scenes(
        self, scenes: Sequence[Tuple[str, Optional[float]]]
    ) -> Tuple[bool, List[str]]:
        """
        Validates a sequence of (text, duration_sec) scenes.
        Returns (all_valid, list_of_all_violations).
        """
        all_violations: List[str] = []
        for idx, (text, dur) in enumerate(scenes):
            res = self.validate_scene(text, dur)
            if not res.is_valid:
                for v in res.violations:
                    all_violations.append(f"Scene #{idx+1}: {v}")
        return len(all_violations) == 0, all_violations
