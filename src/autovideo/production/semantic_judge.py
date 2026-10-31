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
