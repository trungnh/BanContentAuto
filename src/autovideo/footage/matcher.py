"""
Semantic scene -> footage window matcher (ADR-020).

Stage 1 (local, free): CLIP similarity between the scene text and every indexed frame,
         sliding windows of the scene duration, shot-cut / overlap / reuse constraints,
         subject presence and generic-defect penalties -> top-K candidate windows.
Stage 2 (optional, 1 call): the vision LLM picks the best of the top-K from one grid image
         (see SemanticFootageJudge.choose_best). Skipped when CLIP is already confident.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from autovideo.footage.clip_engine import ClipEngine
from autovideo.footage.library import FootageLibrary, VideoIndex
from autovideo.sourcing.relevance import anchor_matches

logger = logging.getLogger(__name__)

# Generic visual defects CLIP can recognise cheaply (penalised, never hard-coded per topic)
DEFECT_PROMPTS: Tuple[str, ...] = (
    "a person talking to the camera",
    "people and a safari vehicle in the foreground",
    "text, captions and a logo on screen",
    "a video player interface or slideshow title card",
    "a video game screenshot",
    "a cartoon or animated drawing",
    "a blurry dark black image",
)


@dataclass
class WindowCandidate:
    video_id: str
    start: float
    end: float
    clip_score: float          # mean query similarity in window
    subject_score: float       # mean subject similarity in window
    defect_score: float        # max defect similarity in window
    total: float               # ranking score
    cuts_inside: int = 0
    llm: Dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class SceneQuery:
    scene_id: str
    duration: float
    texts: List[str]           # visual_prompt + english keywords


class SceneFootageMatcher:
    def __init__(
        self,
        library: FootageLibrary,
        clip: ClipEngine,
        subject_anchor: str,
        subject_min: float = 0.27,
        defect_margin: float = 0.02,
        cut_penalty: float = 0.004,
        max_reuse_per_video: int = 2,
        diversity_threshold: float = 0.92,
        diversity_weight: float = 0.5,
        confuser_margin: float = 0.01,
        confuser_weight: float = 0.5,
    ) -> None:
        self.lib = library
        self.clip = clip
        self.anchor = subject_anchor or ""
        self.subject_min = subject_min
        self.defect_margin = defect_margin
        self.cut_penalty = cut_penalty
        self.max_reuse = max_reuse_per_video
        self.diversity_threshold = diversity_threshold
        self.diversity_weight = diversity_weight
        self.confuser_margin = confuser_margin
        self.confuser_weight = confuser_weight
        self.confusers: List[str] = []
        self._confuser_vecs: Optional[np.ndarray] = None
        self._subject_vec = clip.embed_texts([f"a photo of a {self.anchor}" if self.anchor else "a documentary photo"])[0]
        self._defect_vecs = clip.embed_texts(list(DEFECT_PROMPTS))
        self._cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self._conf_cache: Dict[str, np.ndarray] = {}

    # ------------------------------------------------------------ precompute
    def _per_video(self, vi: VideoIndex) -> Tuple[np.ndarray, np.ndarray]:
        key = vi.entry.video_id
        if key not in self._cache:
            subj = vi.embeddings @ self._subject_vec
            defect = (vi.embeddings @ self._defect_vecs.T).max(axis=1)
            self._cache[key] = (subj, defect)
        return self._cache[key]

    def query_vector(self, texts: Sequence[str]) -> np.ndarray:
        texts = [t for t in texts if t and t.strip()]
        vecs = self.clip.embed_texts([t[:300] for t in texts])
        v = vecs.mean(axis=0)
        return v / max(float(np.linalg.norm(v)), 1e-8)

    def eligible_videos(self) -> List[VideoIndex]:
        anchor_low = self.anchor.lower().strip()
        confusers_low = [c.lower() for c in getattr(self, "confusers", []) or []]
        out = []
        for vi in self.lib.videos.values():
            if getattr(vi.entry, "inauthentic", False):
                continue
            text = vi.entry.text()
            if not anchor_matches(text, self.anchor):
                continue
            # ADR-021: a video explicitly about a look-alike species (e.g. 'Striped Hyena walking') is not
            # footage of the subject, unless it also names the subject itself.
            low = text.lower()
            if confusers_low and anchor_low and anchor_low not in low and any(c in low for c in confusers_low):
                continue
            out.append(vi)
        return out

    # ----------------------------------------------------------------- match
    def set_confusers(self, names: Sequence[str]) -> None:
        """Visually similar species/things that must NOT count as the subject (e.g. jackal for hyena)."""
        names = [n.strip() for n in names if n and n.strip()]
        self.confusers = names
        self._confuser_vecs = self.clip.embed_texts([f"a photo of a {n}" for n in names]) if names else None
        self._conf_cache.clear()

    def _per_video_conf(self, vi: VideoIndex) -> Optional[np.ndarray]:
        if getattr(self, "_confuser_vecs", None) is None:
            return None
        key = f"conf:{vi.entry.video_id}"
        if key not in self._conf_cache:
            self._conf_cache[key] = (vi.embeddings @ self._confuser_vecs.T).max(axis=1)
        return self._conf_cache[key]

    def window_embedding(self, video_id: str, start: float, end: float) -> Optional[np.ndarray]:
        vi = self.lib.videos.get(video_id)
        if vi is None or len(vi.times) == 0:
            return None
        mask = (vi.times >= start) & (vi.times <= end)
        if not mask.any():
            mask = np.abs(vi.times - (start + end) / 2) == np.abs(vi.times - (start + end) / 2).min()
        v = vi.embeddings[mask].mean(axis=0)
        return v / max(float(np.linalg.norm(v)), 1e-8)

    def diversity_penalty(self, emb: Optional[np.ndarray], avoid: Optional[np.ndarray]) -> float:
        if emb is None or avoid is None or len(avoid) == 0:
            return 0.0
        sim = float((avoid @ emb).max())
        return max(0.0, sim - self.diversity_threshold) * self.diversity_weight

    def top_windows(
        self,
        q: SceneQuery,
        used_intervals: Dict[str, List[Tuple[float, float]]],
        used_counts: Dict[str, int],
        top_k: int = 4,
        per_video: int = 1,
        avoid_embeddings: Optional[np.ndarray] = None,
        query_vec: Optional[np.ndarray] = None,
    ) -> List[WindowCandidate]:
        """Best windows across the library (up to `per_video` non-overlapping windows per video)."""
        qv = query_vec if query_vec is not None else self.query_vector(q.texts)
        out: List[WindowCandidate] = []
        for vi in self.eligible_videos():
            vid = vi.entry.video_id
            if used_counts.get(vid, 0) >= self.max_reuse:
                continue
            if vi.duration_sec < q.duration + 0.1 or len(vi.times) < 2:
                continue
            sims = vi.embeddings @ qv
            subj, defect = self._per_video(vi)
            conf = self._per_video_conf(vi)
            step = float(vi.times[1] - vi.times[0]) if len(vi.times) > 1 else 1.0
            win = max(1, int(math.ceil(q.duration / step)))
            if len(vi.times) < win:
                continue
            kernel = np.ones(win, dtype=np.float32) / win
            c_roll = np.convolve(sims, kernel, mode="valid")
            s_roll = np.convolve(subj, kernel, mode="valid")
            d_roll = np.lib.stride_tricks.sliding_window_view(defect, win).max(axis=1)
            starts = np.maximum(0.0, vi.times[: len(c_roll)] - step / 2)
            ends = starts + q.duration

            valid = (ends <= vi.duration_sec) & (s_roll >= self.subject_min)
            for s, e in used_intervals.get(vid, []):
                valid &= ~((starts < e) & (ends > s))
            if not valid.any():
                continue

            cuts = np.sort(np.array(vi.cuts, dtype=np.float32))
            if len(cuts):
                n_cuts = np.searchsorted(cuts, ends - 0.3) - np.searchsorted(cuts, starts + 0.3, side="right")
                n_cuts = np.maximum(n_cuts, 0)
            else:
                n_cuts = np.zeros_like(starts, dtype=np.int64)
            penalty = n_cuts * self.cut_penalty + np.maximum(0.0, d_roll - s_roll + self.defect_margin)
            if conf is not None:
                conf_roll = np.convolve(conf, kernel, mode="valid")
                penalty = penalty + np.maximum(0.0, conf_roll - s_roll - self.confuser_margin) * self.confuser_weight
            total = np.where(valid, c_roll - penalty, -np.inf)

            picked = 0
            order = np.argsort(-total)
            taken: List[Tuple[float, float]] = []
            for i in order:
                if not np.isfinite(total[i]) or picked >= per_video:
                    break
                st, en = float(starts[i]), float(ends[i])
                if any(st < e and en > s for s, e in taken):
                    continue
                cand = WindowCandidate(vid, round(st, 2), round(en, 2), float(c_roll[i]), float(s_roll[i]),
                                       float(d_roll[i]), float(total[i]), int(n_cuts[i]))
                if avoid_embeddings is not None:
                    pen = self.diversity_penalty(self.window_embedding(vid, st, en), avoid_embeddings)
                    if pen:
                        cand.total -= pen
                        cand.llm["diversity_penalty"] = round(pen, 4)
                out.append(cand)
                taken.append((st, en))
                picked += 1
        out.sort(key=lambda c: c.total, reverse=True)
        return out[:top_k]

    def candidates(
        self,
        q: SceneQuery,
        used_intervals: Dict[str, List[Tuple[float, float]]],
        used_counts: Dict[str, int],
        top_k: int = 4,
        avoid_embeddings: Optional[np.ndarray] = None,
    ) -> List[WindowCandidate]:
        """Best window per video (backward-compatible API)."""
        return self.top_windows(q, used_intervals, used_counts, top_k=top_k, per_video=1,
                                avoid_embeddings=avoid_embeddings)

    def used_embeddings(self, used_intervals: Dict[str, List[Tuple[float, float]]]) -> Optional[np.ndarray]:
        """CLIP embeddings of every window already used (keys that are library video_ids)."""
        embs = []
        for vid, ivs in used_intervals.items():
            if vid not in self.lib.videos:
                continue
            for s, e in ivs:
                v = self.window_embedding(vid, s, e)
                if v is not None:
                    embs.append(v)
        return np.stack(embs) if embs else None

    # --------------------------------------------------------------- planner
    def plan(
        self,
        queries: List[SceneQuery],
        used_intervals: Dict[str, List[Tuple[float, float]]],
        used_counts: Dict[str, int],
        k: int = 12,
        per_video: int = 3,
        alternatives: int = 6,
    ) -> Dict[str, List[WindowCandidate]]:
        """
        Global shot assignment (regret greedy): repeatedly assign the scene that would lose the most
        if it did not get its best feasible window. Prevents early scenes from consuming footage that
        later scenes need more (e.g. 'nursing' footage). Returns scene_id -> [assigned, alternatives...].
        """
        pools = {q.scene_id: self.top_windows(q, used_intervals, used_counts, top_k=k, per_video=per_video)
                 for q in queries}
        iv: Dict[str, List[Tuple[float, float]]] = {key: list(v) for key, v in used_intervals.items()}
        counts = dict(used_counts)
        avoid_list: List[np.ndarray] = []
        base = self.used_embeddings(used_intervals)
        if base is not None:
            avoid_list.extend(list(base))
        emb_cache: Dict[Tuple[str, float], Optional[np.ndarray]] = {}

        def _emb(c: WindowCandidate) -> Optional[np.ndarray]:
            key = (c.video_id, c.start)
            if key not in emb_cache:
                emb_cache[key] = self.window_embedding(c.video_id, c.start, c.end)
            return emb_cache[key]

        def _feasible(c: WindowCandidate) -> bool:
            if counts.get(c.video_id, 0) >= self.max_reuse:
                return False
            return not any(c.start < e and c.end > s for s, e in iv.get(c.video_id, []))

        def _score(c: WindowCandidate) -> float:
            avoid = np.stack(avoid_list) if avoid_list else None
            return c.total - self.diversity_penalty(_emb(c), avoid)

        result: Dict[str, List[WindowCandidate]] = {}
        remaining = set(pools)
        while remaining:
            best_sid, best_regret, best_list = None, -math.inf, []
            for sid in remaining:
                ranked = sorted(((_score(c), c) for c in pools[sid] if _feasible(c)), key=lambda t: t[0], reverse=True)
                if not ranked:
                    regret = math.inf  # nothing left: settle it now (empty plan -> online / last resort)
                else:
                    s2 = ranked[1][0] if len(ranked) > 1 else ranked[0][0] - 0.05
                    regret = ranked[0][0] - s2
                if regret > best_regret:
                    best_sid, best_regret, best_list = sid, regret, ranked
            remaining.discard(best_sid)
            if not best_list:
                result[best_sid] = []
                continue
            chosen = best_list[0][1]
            iv.setdefault(chosen.video_id, []).append((chosen.start, chosen.end))
            counts[chosen.video_id] = counts.get(chosen.video_id, 0) + 1
            e = _emb(chosen)
            if e is not None:
                avoid_list.append(e)
            result[best_sid] = [chosen] + [c for _, c in best_list[1:1 + alternatives]]
        return result

    def with_subject_min(self, subject_min: float) -> "SceneFootageMatcher":
        """Shallow copy with a different subject-presence threshold (shares embeddings cache)."""
        import copy
        m = copy.copy(self)
        m.subject_min = subject_min
        return m

    @staticmethod
    def is_confident(cands: List[WindowCandidate], min_score: float = 0.30, margin: float = 0.02) -> bool:
        """CLIP alone is trusted when the winner is strong and clearly ahead (skip the LLM call)."""
        if not cands:
            return False
        if len(cands) == 1:
            return cands[0].total >= min_score
        return cands[0].total >= min_score and (cands[0].total - cands[1].total) >= margin
