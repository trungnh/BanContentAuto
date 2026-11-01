"""
Semantic Footage Judge (ADR-019).

Title/metadata heuristics can only prove a video *mentions* the subject; they cannot
prove the cut segment *shows* what the narration says. This judge samples frames from
the exact segment that will be used and asks a multimodal LLM to score the match.

Verdicts:
- "pass":        subject visible, real footage, no overlays (if enforced), score >= min_score
- "fail":        judged and rejected (reason recorded)
- "unavailable": judge disabled / API error -> caller falls back to metadata gates and
                 records `semantic_check=unavailable` so the gap is visible, never silent.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import httpx

from autovideo.production.visual_inspector import VisualQualityInspector

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class SemanticJudgeResult:
    verdict: str  # "pass" | "fail" | "unavailable"
    score: float = 0.0
    subject_present: bool = False
    is_real_footage: bool = True
    has_overlay: bool = False
    reason: str = ""
    sampled_offsets: List[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_judge_prompt(narration: str, visual_prompt: str, subject_anchor: str) -> str:
    return (
        "You are a strict footage editor for a factual documentary.\n"
        f"Main subject: {subject_anchor or 'unspecified'}\n"
        f"Narration for this shot (may be Vietnamese): {narration}\n"
        f"Desired shot description: {visual_prompt or '(none)'}\n\n"
        "The attached images are frames sampled in order from ONE candidate clip.\n"
        "Judge whether the clip illustrates the MEANING of the narration (subject + action/situation).\n"
        "Do NOT penalize cinematography details (time of day, lens, camera angle, lighting, exact framing).\n"
        "Return ONLY a JSON object, no prose:\n"
        "{\n"
        '  "subject_present": true/false,   // main subject clearly visible in at least 2 frames\n'
        '  "is_real_footage": true/false,   // false for cartoon, animation, video game, CGI, slideshow, talking-head studio\n'
        '  "overlay_text_or_watermark": true/false, // burned-in captions, titles, channel/TV logos, watermarks\n'
        '  "match_score": 0-10,             // how well the frames illustrate the narration/desired shot.\n'
        "                                   // 0-2 wrong subject/people/game/screen; 3-4 subject present but unrelated action;\n"
        "                                   // 5-6 subject in plausible related context; 7-8 clearly related action; 9-10 exact\n"
        '  "reason": "short explanation"\n'
        "}"
    )


def parse_judge_response(raw: str) -> Dict[str, Any]:
    m = _JSON_RE.search(raw or "")
    if not m:
        raise ValueError(f"Judge returned no JSON: {raw[:200]!r}")
    text = re.sub(r"//[^\n]*", "", m.group(0))
    return json.loads(text)


class SemanticFootageJudge:
    """Multimodal relevance gate for candidate footage segments."""

    MAX_CONSECUTIVE_ERRORS = 3

    def __init__(
        self,
        enabled: bool = True,
        provider: str = "9router",
        api_key: str = "",
        base_url: str = "http://localhost:20128/v1",
        model: str = "",
        min_score: float = 6.0,
        reject_overlays: bool = True,
        timeout_sec: float = 60.0,
        frame_width: int = 512,
    ) -> None:
        self.enabled = enabled
        self.provider = provider
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.min_score = float(min_score)
        self.reject_overlays = reject_overlays
        self.timeout_sec = timeout_sec
        self.frame_width = frame_width
        self._consecutive_errors = 0
        self.calls = 0

    @classmethod
    def from_settings(cls, settings: Any) -> "SemanticFootageJudge":
        provider = getattr(settings, "llm_provider", "9router")
        model = getattr(settings, "semantic_judge_model", "") or getattr(settings, "llm_model", "")
        if provider == "gemini":
            api_key = getattr(settings, "gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")
            base_url = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        else:
            api_key = getattr(settings, "ninerouter_api_key", "") or os.getenv("NINEROUTER_API_KEY", "")
            base_url = getattr(settings, "ninerouter_base_url", "") or "http://localhost:20128/v1"
        return cls(
            enabled=bool(getattr(settings, "semantic_judge_enabled", True)) and provider in ("9router", "gemini"),
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            min_score=float(getattr(settings, "semantic_judge_min_score", 6)),
            reject_overlays=bool(getattr(settings, "semantic_judge_reject_overlays", True)),
        )

    @property
    def active(self) -> bool:
        return (
            self.enabled
            and bool(self.model)
            and bool(self.api_key)
            and self._consecutive_errors < self.MAX_CONSECUTIVE_ERRORS
        )

    # ------------------------------------------------------------------ frames
    def _sample_frames(
        self, video_path: Path, start_sec: float, duration_sec: float, ffmpeg_bin: Optional[Path]
    ) -> tuple[List[str], List[float]]:
        offsets = [start_sec + duration_sec * r for r in (0.15, 0.5, 0.85)]
        images: List[str] = []
        used: List[float] = []
        for off in offsets:
            frame = VisualQualityInspector._extract_frame(video_path, off, ffmpeg_bin=ffmpeg_bin)
            if frame is None:
                continue
            h, w = frame.shape[:2]
            if w > self.frame_width:
                frame = cv2.resize(frame, (self.frame_width, int(h * self.frame_width / w)))
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                images.append(base64.b64encode(buf.tobytes()).decode("ascii"))
                used.append(round(off, 2))
        return images, used

    # --------------------------------------------------------------- transport
    def _call_ninerouter(self, prompt: str, images_b64: List[str]) -> str:
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}})
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.0,
            "max_tokens": 400,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Judge HTTP {resp.status_code}: {resp.text[:200]}")
        raw = resp.text.strip()
        if raw.startswith("data:"):
            chunks = []
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:") and line[5:].strip() != "[DONE]":
                    try:
                        delta = json.loads(line[5:].strip())["choices"][0].get("delta", {})
                        chunks.append(delta.get("content") or "")
                    except Exception:
                        continue
            return "".join(chunks)
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt: str, images_b64: List[str]) -> str:
        parts: List[Dict[str, Any]] = [{"text": prompt}]
        for img in images_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img}})
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0}}
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Judge HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    # -------------------------------------------------------------- text calls
    def _call_text(self, prompt: str) -> str:
        if self.provider == "gemini":
            return self._call_gemini(prompt, [])
        return self._call_ninerouter(prompt, [])

    def suggest_confusers(self, subject_anchor: str, max_items: int = 5) -> List[str]:
        """ONE text call: visually similar animals/objects a footage search may confuse with the subject."""
        if not self.active or not subject_anchor:
            return []
        prompt = (
            f"List up to {max_items} animals or objects that look visually similar to a '{subject_anchor}' in "
            "wildlife video footage and could be mistaken for it (e.g. similar species). English names only.\n"
            'Return ONLY JSON: {"confusers": ["...", "..."]}'
        )
        try:
            self.calls += 1
            data = parse_judge_response(self._call_text(prompt))
            items = [str(x).strip() for x in (data.get("confusers") or []) if str(x).strip()]
            anchor_low = subject_anchor.lower()
            return [x for x in items if x.lower() != anchor_low][:max_items]
        except Exception as exc:
            logger.warning("suggest_confusers lỗi: %s", exc)
            return []

    def rewrite_visual_prompts(
        self, items: List[Dict[str, Any]], inventory_titles: List[str], subject_anchor: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        ONE batched text call (ADR-021 footage-aware shots): for scenes whose desired shot is not available,
        propose a filmable alternative shot that still illustrates the narration, phrased for the existing
        footage inventory. items: [{"scene_id","narration","visual_prompt"}].
        Returns {scene_id: {"visual_prompt": str, "keywords": [str, str]}}.
        """
        if not self.active or not items:
            return {}
        lines = "\n".join(
            f'- {it["scene_id"]}: narration="{str(it["narration"])[:300]}" | current shot="{str(it["visual_prompt"])[:200]}"'
            for it in items
        )
        inventory = "\n".join(f"* {t[:90]}" for t in inventory_titles[:60])
        prompt = (
            f"You edit a documentary about: {subject_anchor}.\n"
            "The desired shots below are NOT available in our footage library. For each scene, write a NEW shot "
            "description that (1) still illustrates the meaning of the narration, (2) shows real footage of the "
            f"{subject_anchor} doing something plausible, and (3) is likely to exist in this library:\n"
            f"{inventory}\n\nScenes:\n{lines}\n\n"
            "Rules: English, one sentence per visual_prompt, concrete visible action, no MRI/CGI/diagrams/text, "
            f"always include '{subject_anchor}'. Give 2 short search keywords per scene.\n"
            'Return ONLY JSON: {"scenes": {"SCENE_001": {"visual_prompt": "...", "keywords": ["...", "..."]}}}'
        )
        try:
            self.calls += 1
            data = parse_judge_response(self._call_text(prompt))
            out: Dict[str, Dict[str, Any]] = {}
            for sid, v in (data.get("scenes") or {}).items():
                if isinstance(v, dict) and str(v.get("visual_prompt") or "").strip():
                    out[str(sid)] = {
                        "visual_prompt": str(v["visual_prompt"]).strip(),
                        "keywords": [str(k).strip() for k in (v.get("keywords") or []) if str(k).strip()][:3],
                    }
            return out
        except Exception as exc:
            logger.warning("rewrite_visual_prompts lỗi: %s", exc)
            return {}

    # -------------------------------------------------------------- choose best
    def _grid_image(
        self, candidates: List[Dict[str, Any]], ffmpeg_bin: Optional[Path], tile_w: int = 288
    ) -> Optional[str]:
        """One JPEG: one labelled row (A, B, C...) of 4 frames per candidate window."""
        import numpy as np

        tile_h = tile_w * 9 // 16
        rows = []
        for idx, c in enumerate(candidates):
            frames = []
            for r in (0.15, 0.4, 0.65, 0.9):
                f = VisualQualityInspector._extract_frame(Path(c["path"]), c["start"] + c["duration"] * r, ffmpeg_bin)
                frames.append(cv2.resize(f, (tile_w, tile_h)) if f is not None else np.zeros((tile_h, tile_w, 3), np.uint8))
            label = np.full((tile_h, 60, 3), 25, np.uint8)
            cv2.putText(label, chr(65 + idx), (14, tile_h // 2 + 14), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
            rows.append(np.hstack([label] + frames))
        if not rows:
            return None
        ok, buf = cv2.imencode(".jpg", np.vstack(rows), [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None

    def choose_best(
        self,
        candidates: List[Dict[str, Any]],
        narration: str,
        visual_prompt: str,
        subject_anchor: str,
        ffmpeg_bin: Optional[Path] = None,
        confusers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        ONE vision call for up to ~4 candidate windows (each dict: path, start, duration).
        Returns {"verdict": pass|fail|unavailable, "index": int|None, "score": float, "scores": {...}, "reason": str}.
        """
        if not self.active:
            return {"verdict": "unavailable", "index": None, "score": 0.0, "reason": "judge disabled or circuit open"}
        img = self._grid_image(candidates, ffmpeg_bin)
        if not img:
            return {"verdict": "fail", "index": None, "score": 0.0, "reason": "no frames"}
        letters = [chr(65 + i) for i in range(len(candidates))]
        confuser_rule = ""
        if confusers:
            confuser_rule = (
                f"SPECIES CHECK: look carefully at the animal. {', '.join(confusers)} are NOT a {subject_anchor}; "
                "a row showing those instead of the subject is unusable.\n"
            )
        prompt = (
            "You are a strict footage editor for a factual documentary.\n"
            f"Main subject: {subject_anchor or 'unspecified'}\n"
            f"Narration for this shot (may be Vietnamese): {narration}\n"
            f"Desired shot description: {visual_prompt or '(none)'}\n\n"
            f"The image has {len(candidates)} labelled rows ({', '.join(letters)}). Each row = frames from one candidate clip, "
            "exactly as it will appear in the video.\n"
            "Judge how well each row illustrates the MEANING of the narration (subject + action/situation). "
            "Ignore cinematography details (time of day, lens, angle).\n"
            + confuser_rule +
            "A row is unusable if the main subject is absent or not clearly identifiable, the image is blurry, "
            "it is not real footage (cartoon, game, CGI/AI-generated, slideshow, talking head), or it has burned-in "
            "captions / channel logos / watermarks.\n"
            "Return ONLY JSON:\n"
            '{"scores": {"A": 0-10, ...}, "unusable": ["B", ...], "ai_generated": ["C", ...], '
            '"best": "A" or "none", "reason": "short"}\n'
            '"ai_generated" lists rows that look AI-generated / CGI (they must also be in "unusable").'
        )
        raw = None
        last_exc: Optional[Exception] = None
        for attempt in range(2):  # one retry: 9Router occasionally times out on image requests
            try:
                self.calls += 1
                if self.provider == "gemini":
                    raw = self._call_gemini(prompt, [img])
                else:
                    raw = self._call_ninerouter(prompt, [img])
                break
            except Exception as exc:
                last_exc = exc
                transient = "timed out" in str(exc).lower() or "timeout" in str(exc).lower() or "502" in str(exc) or "503" in str(exc)
                if attempt == 0 and transient:
                    logger.warning("choose_best: lỗi tạm thời (%s) — thử lại 1 lần", str(exc)[:80])
                    self.timeout_sec = max(self.timeout_sec, 90.0)
                    continue
                break
        try:
            if raw is None:
                raise last_exc or RuntimeError("judge returned nothing")
            data = parse_judge_response(raw)
            self._consecutive_errors = 0
        except Exception as exc:
            self._consecutive_errors += 1
            logger.warning("SemanticFootageJudge.choose_best unavailable (%d/%d): %s",
                           self._consecutive_errors, self.MAX_CONSECUTIVE_ERRORS, exc)
            return {"verdict": "unavailable", "index": None, "score": 0.0, "reason": str(exc)[:200]}

        scores = {str(k).upper(): float(v or 0) for k, v in (data.get("scores") or {}).items()}
        ai_rows = {str(x).upper() for x in (data.get("ai_generated") or [])}
        unusable = {str(x).upper() for x in (data.get("unusable") or [])} | ai_rows
        best = str(data.get("best") or "none").upper()
        usable = {k: v for k, v in scores.items() if k in letters and k not in unusable}
        if best not in usable:
            best = max(usable, key=usable.get) if usable else "NONE"
        score = usable.get(best, 0.0)
        idx = letters.index(best) if best in letters else None
        verdict = "pass" if idx is not None and score >= self.min_score else "fail"
        return {"verdict": verdict, "index": idx, "score": score, "scores": scores,
                "unusable": sorted(unusable), "ai_generated_indices": sorted(letters.index(r) for r in ai_rows if r in letters),
                "reason": str(data.get("reason") or "")[:300]}

    # -------------------------------------------------------------------- main
    def judge(
        self,
        video_path: Path,
        start_sec: float,
        duration_sec: float,
        narration: str,
        visual_prompt: str,
        subject_anchor: str,
        ffmpeg_bin: Optional[Path] = None,
    ) -> SemanticJudgeResult:
        if not self.active:
            return SemanticJudgeResult(verdict="unavailable", reason="judge disabled or circuit open")
        # Same convention as VisualQualityInspector: <1KB files are unit-test stubs, not real media
        if not video_path.exists() or video_path.stat().st_size < 1024:
            return SemanticJudgeResult(verdict="unavailable", reason="stub or missing media file")

        images, used = self._sample_frames(video_path, start_sec, duration_sec, ffmpeg_bin)
        if len(images) < 2:
            return SemanticJudgeResult(verdict="fail", reason="could not decode frames in segment", sampled_offsets=used)

        prompt = build_judge_prompt(narration, visual_prompt, subject_anchor)
        try:
            self.calls += 1
            raw = self._call_gemini(prompt, images) if self.provider == "gemini" else self._call_ninerouter(prompt, images)
            data = parse_judge_response(raw)
            self._consecutive_errors = 0
        except Exception as exc:
            self._consecutive_errors += 1
            logger.warning("SemanticFootageJudge unavailable (%d/%d): %s",
                           self._consecutive_errors, self.MAX_CONSECUTIVE_ERRORS, exc)
            return SemanticJudgeResult(verdict="unavailable", reason=str(exc)[:200], sampled_offsets=used)

        score = float(data.get("match_score") or 0.0)
        subject = bool(data.get("subject_present"))
        real = bool(data.get("is_real_footage", True))
        overlay = bool(data.get("overlay_text_or_watermark"))
        reason = str(data.get("reason") or "")[:300]

        passed = subject and real and score >= self.min_score and not (self.reject_overlays and overlay)
        return SemanticJudgeResult(
            verdict="pass" if passed else "fail",
            score=score,
            subject_present=subject,
            is_real_footage=real,
            has_overlay=overlay,
            reason=reason,
            sampled_offsets=used,
        )
