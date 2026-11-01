"""
Library-first scene footage picker (ADR-020).

Flow per scene:
  CLIP top-K windows (local) -> visual QA (local ffmpeg/cv) ->
  confident? accept : ONE vision-LLM call choose_best() -> pass? accept : keep as fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autovideo.footage.library import FootageLibrary
from autovideo.footage.matcher import SceneFootageMatcher, SceneQuery, WindowCandidate
from autovideo.production.semantic_judge import SemanticFootageJudge
from autovideo.production.visual_inspector import VisualQualityInspector
from autovideo.sourcing.engine import SourcedAsset

logger = logging.getLogger(__name__)


def library_sourced_asset(lib: FootageLibrary, cand: WindowCandidate, scene_id: str, subject_anchor: str) -> SourcedAsset:
    vi = lib.videos[cand.video_id]
    e = vi.entry
    return SourcedAsset(
        scene_id=scene_id,
        query=f"library:{cand.video_id}@{cand.start:.1f}",
        file_path=e.path,
        duration_sec=vi.duration_sec,
        width=1920,
        height=1080,
        vault_source="library",
        is_watermark_clean=True,
        metadata={
            "extractor": "youtube",
            "video_id": e.video_id,
            "title": e.title,
            "webpage_url": e.webpage_url or f"https://www.youtube.com/watch?v={e.video_id}",
            "uploader": e.uploader,
            "raw_filename": e.path.name,
            "description": e.description[:1500],
            "subject_anchor": subject_anchor,
            "effective_query": f"clip-library:{cand.video_id}",
            "chapters": None,
            "categories": None,
        },
    )


def pick_library_window(
    *,
    lib: FootageLibrary,
    matcher: SceneFootageMatcher,
    judge: SemanticFootageJudge,
    scene_id: str,
    duration: float,
    narration: str,
    visual_prompt: str,
    en_keywords: List[str],
    subject_anchor: str,
    used_intervals: Dict[str, List[Tuple[float, float]]],
    used_counts: Dict[str, int],
    ffmpeg_bin: Optional[Path],
    top_k: int = 4,
    candidates_override: Optional[List[WindowCandidate]] = None,
    exclude_windows: Optional[List[Tuple[str, float, float]]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Returns (accepted, fallback). Each is a dict compatible with the coordinator's accepted-candidate
    format: {"path", "sourced", "offset", "semantic", "library"}. Either may be None.

    candidates_override: pre-ranked windows from the global planner (ADR-021); re-validated here against
    the windows used so far. exclude_windows: (video_id, start, end) that must not be picked (e.g. the
    scene's current footage when the user asks to redo it).
    """
    texts = [visual_prompt] + list(en_keywords or [])
    blocked = list(exclude_windows or [])

    def _ok(c: WindowCandidate) -> bool:
        if used_counts.get(c.video_id, 0) >= matcher.max_reuse:
            return False
        if any(c.start < e and c.end > s for s, e in used_intervals.get(c.video_id, [])):
            return False
        if any(v == c.video_id and c.start < e and c.end > s for v, s, e in blocked):
            return False
        vi = lib.videos.get(c.video_id)
        return vi is not None and not getattr(vi.entry, "inauthentic", False)

    cands: List[WindowCandidate] = [c for c in (candidates_override or []) if _ok(c)]
    if len(cands) < top_k:
        avoid = matcher.used_embeddings(used_intervals)
        extra_iv = {k: list(v) for k, v in used_intervals.items()}
        for v, s, e in blocked:
            extra_iv.setdefault(v, []).append((s, e))
        fresh = matcher.top_windows(SceneQuery(scene_id, duration, texts), extra_iv, used_counts,
                                    top_k=top_k * 2, per_video=2, avoid_embeddings=avoid)
        seen = {(c.video_id, c.start) for c in cands}
        cands += [c for c in fresh if (c.video_id, c.start) not in seen and _ok(c)]

    clean: List[WindowCandidate] = []
    for c in cands:
        res = VisualQualityInspector.inspect_video_segment(
            video_path=lib.videos[c.video_id].entry.path, start_sec=c.start, duration_sec=duration, ffmpeg_bin=ffmpeg_bin,
        )
        if res.is_clean:
            clean.append(c)
        else:
            logger.info("Library window %s@%.1f loại do lỗi thị giác %s", c.video_id, c.start, res.defects)
        if len(clean) >= top_k:
            break
    if not clean:
        logger.info("Footage library: không có cửa sổ phù hợp cho %s", scene_id)
        return None, None

    def _pack(c: WindowCandidate, semantic: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "path": lib.videos[c.video_id].entry.path,
            "sourced": library_sourced_asset(lib, c, scene_id, subject_anchor),
            "offset": c.start,
            "semantic": semantic,
            "library": {
                "video_id": c.video_id, "start": c.start, "end": c.end, "clip_score": round(c.clip_score, 4),
                "subject_score": round(c.subject_score, 4), "defect_score": round(c.defect_score, 4),
                "rank_score": round(c.total, 4), "cuts_inside": c.cuts_inside,
                "alternatives": [(a.video_id, a.start, round(a.total, 4)) for a in clean[1:]],
            },
        }

    if SceneFootageMatcher.is_confident(clean):
        logger.info("Library %s: CLIP tự tin (%.3f vs %.3f) -> bỏ qua LLM", scene_id, clean[0].total,
                    clean[1].total if len(clean) > 1 else 0.0)
        return _pack(clean[0], {"verdict": "clip_confident", "score": round(clean[0].total, 4), "method": "clip"}), None

    payload = [{"path": str(lib.videos[c.video_id].entry.path), "start": c.start, "duration": duration} for c in clean]
    choice = judge.choose_best(payload, narration, visual_prompt, subject_anchor, ffmpeg_bin,
                               confusers=getattr(matcher, "confusers", None) or None)
    if choice.get("verdict") == "unavailable":
        logger.warning("Library %s: judge không khả dụng -> dùng top CLIP", scene_id)
        return _pack(clean[0], {"verdict": "unavailable", "score": round(clean[0].total, 4), "method": "clip",
                                "reason": choice.get("reason")}), None

    idx = choice.get("index")
    for ai_idx in choice.get("ai_generated_indices") or []:
        if 0 <= ai_idx < len(clean) and hasattr(lib, "flag_inauthentic"):
            lib.flag_inauthentic(clean[ai_idx].video_id)
    semantic = {"verdict": choice["verdict"], "score": choice.get("score", 0.0), "method": "llm_choose_best",
                "scores": choice.get("scores"), "unusable": choice.get("unusable"), "reason": choice.get("reason")}
    if idx is None:
        logger.warning("Library %s: LLM loại cả %d ứng viên (%s)", scene_id, len(clean), choice.get("reason"))
        return None, None
    picked = _pack(clean[idx], semantic)
    if choice["verdict"] == "pass":
        logger.info("Library %s: LLM chọn %s (score=%.1f)", scene_id, chr(65 + idx), choice.get("score", 0))
        return picked, None
    logger.info("Library %s: LLM chọn %s nhưng dưới ngưỡng (score=%.1f) -> giữ làm dự phòng", scene_id, chr(65 + idx),
                choice.get("score", 0))
    return None, picked
