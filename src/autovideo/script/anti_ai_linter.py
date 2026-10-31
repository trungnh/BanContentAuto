"""
Anti-AI Linter and Burstiness Rhythm Verifier (REQ-B1-02).
Detects 35 AI cliché patterns derived from Wikipedia AI Cleanup,
calculates sentence length burstiness coefficient of variation (Cv >= 0.4),
and enforces sentence length rhythm (no 3 consecutive sentences within +-3 words).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple


# BANNED_PATTERNS_35 is retired per user decision (Option 3: zero static blacklist).
# Static word blacklisting is eliminated in favor of AI-native Skill Niche prompt styling.
# Kept as empty tuple for backward compatibility with imports.
BANNED_PATTERNS_35: Tuple[str, ...] = ()


@dataclass
class LintResult:
    """Detailed results of Anti-AI and sentence rhythm linting."""

    passed: bool
    cv: float
    sentence_count: int
    sentence_lengths: List[int]
    banned_matches: List[str] = field(default_factory=list)
    has_consecutive_same_length: bool = False
    consecutive_violations: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)


class AntiAILinter:
    """
    Quality gate linter for natural, humanized scriptwriting.
    Validates anti-AI pattern hygiene and sentence burstiness.
    """

    def __init__(
        self,
        banned_patterns: Sequence[str] = BANNED_PATTERNS_35,
        min_cv: float = 0.4,
        consecutive_length_tolerance: int = 3,
    ) -> None:
        self.banned_patterns = tuple(banned_patterns)
        self.min_cv = min_cv
        self.consecutive_length_tolerance = consecutive_length_tolerance

        # Precompile regex for banned patterns
        self._compiled_patterns: List[Tuple[str, re.Pattern]] = []
        for pat in self.banned_patterns:
            if any(char in pat for char in (r"\s+", ".+?", r"\w+")):
                # Pattern is already regex
                regex = re.compile(pat, re.IGNORECASE)
            else:
                # Treat as literal phrase, allowing arbitrary internal whitespace
                escaped = re.escape(pat).replace(r"\ ", r"\s+")
                regex = re.compile(escaped, re.IGNORECASE)
            self._compiled_patterns.append((pat, regex))

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """
        Splits text into complete sentences while preserving Vietnamese numbers and abbreviations.
        Handles '.', '!', '?', and ellipses.
        """
        # Protect common abbreviations and decimal numbers (e.g., 3.5 tấn, TP.HCM, Q.1)
        protected = text
        protected = re.sub(r"(\d+)\.(\d+)", r"\1__DECIMAL_DOT__\2", protected)
        protected = re.sub(r"\bTP\.", "TP__DOT__", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bTS\.", "TS__DOT__", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bThS\.", "ThS__DOT__", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bGS\.", "GS__DOT__", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bPGS\.", "PGS__DOT__", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bMr\.", "Mr__DOT__", protected, flags=re.IGNORECASE)

        # Split on sentence terminals
        raw_parts = re.split(r"(?<=[.!?…])\s+", protected)

        sentences: List[str] = []
        for part in raw_parts:
            # Restore protected dots
            restored = (
                part.replace("__DECIMAL_DOT__", ".")
                .replace("TP__DOT__", "TP.")
                .replace("TS__DOT__", "TS.")
                .replace("ThS__DOT__", "ThS.")
                .replace("GS__DOT__", "GS.")
                .replace("PGS__DOT__", "PGS.")
                .replace("Mr__DOT__", "Mr.")
                .strip()
            )
            if restored:
                sentences.append(restored)
        return sentences

    @staticmethod
    def count_words(sentence: str) -> int:
        """Counts words in a sentence based on whitespace."""
        tokens = sentence.split()
        return len(tokens)

    def calculate_cv(self, lengths: Sequence[int]) -> float:
        """
        Calculates the coefficient of variation (Cv = sigma / mu) for sentence lengths.
        Returns 0.0 if fewer than 2 sentences or if mean is 0.
        """
        if len(lengths) < 2:
            return 0.0
        mean = statistics.mean(lengths)
        if mean <= 0:
            return 0.0
        stdev = statistics.stdev(lengths)
        return round(stdev / mean, 4)

    def check_consecutive_lengths(
        self, lengths: Sequence[int]
    ) -> Tuple[bool, List[str]]:
        """
        Checks if any 3 consecutive sentences have nearly identical lengths
        (max - min <= consecutive_length_tolerance, default +-3 words).
        """
        violations: List[str] = []
        if len(lengths) < 3:
            return False, violations

        for i in range(len(lengths) - 2):
            w = lengths[i : i + 3]
            diff = max(w) - min(w)
            if diff <= self.consecutive_length_tolerance:
                violations.append(
                    f"Sentences {i+1}-{i+3} have monotonous lengths ({w[0]}, {w[1]}, {w[2]} words; range={diff} <= {self.consecutive_length_tolerance})"
                )

        return len(violations) > 0, violations

    def lint_text(self, text: str) -> LintResult:
        """
        Performs full linting on a block of script text or narration:
        1. Checks for presence of 35 banned AI patterns.
        2. Splits into sentences and computes word counts.
        3. Computes burstiness coefficient Cv (requires >= min_cv, e.g. 0.4).
        4. Verifies no 3 consecutive sentences have monotonous lengths (+-3 words).
        """
        violations: List[str] = []

        # 1. Banned patterns detection
        banned_matches: List[str] = []
        for raw_pattern, regex in self._compiled_patterns:
            matches = regex.findall(text)
            if matches:
                # Add human readable pattern
                banned_matches.append(raw_pattern)
                violations.append(f"Contains banned AI pattern: '{raw_pattern}' (found {len(matches)} time(s))")

        # 2. Sentence splitting & word counting
        sentences = self.split_sentences(text)
        lengths = [self.count_words(s) for s in sentences]

        # 3. Burstiness Cv calculation
        cv = self.calculate_cv(lengths)
        if len(lengths) >= 3 and cv < self.min_cv:
            violations.append(
                f"Sentence length burstiness Cv={cv:.4f} is below requirement {self.min_cv:.2f}. "
                "Writing lacks rhythm contrast (needs short punchy sentences mixed with longer ones)."
            )

        # 4. Monotonous consecutive sentence lengths check
        has_monotony, monotony_violations = self.check_consecutive_lengths(lengths)
        if has_monotony:
            violations.extend(monotony_violations)

        passed = len(violations) == 0

        return LintResult(
            passed=passed,
            cv=cv,
            sentence_count=len(sentences),
            sentence_lengths=lengths,
            banned_matches=banned_matches,
            has_consecutive_same_length=has_monotony,
            consecutive_violations=monotony_violations,
            violations=violations,
        )
