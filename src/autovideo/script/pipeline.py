"""
Orchestrator Scriptwriting Pipeline and Screenplay Schema (REQ-B1-01, REQ-B1-04).
Coordinates the Multi-Agent Scriptwriting Brain, performs Anti-AI and Word Budget checks,
and outputs standardized Master Plan screenplay.json and SEO packaging seo.md.
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from autovideo.script.anti_ai_linter import AntiAILinter, LintResult
from autovideo.script.prompts import COLD_OPEN_RULES, COUNTERPOINT_RULES, PersonaRegistry, PromptCompiler
from autovideo.script.word_budget import WordBudgetValidator, compute_compliant_duration, estimate_duration
from autovideo.skills.registry import SkillRegistry


# --- Pydantic Data Models for Screenplay Schema ---

class SceneKeyword(BaseModel):
    """Multi-lingual keywords for asset sourcing in Vaults."""
    vi: List[str] = Field(default_factory=list, description="Vietnamese keywords")
    en: List[str] = Field(default_factory=list, description="English keywords for Stock/Archive")
    zh: List[str] = Field(default_factory=list, description="Chinese keywords for Douyin/Bilibili")


class Scene(BaseModel):
    """Atomic scene model (4s - 8s)."""
    scene_id: str = Field(..., description="Unique scene identifier, e.g., SCENE_001")
    chapter_index: int = Field(1, description="Chapter index to which this scene belongs")
    cluster_id: str = Field("cluster_001", description="Spatial scene cluster ID for visual continuity")
    environment_id: str = Field("default_env", description="Environment/setting anchor (e.g. zoo_cage, rainforest)")
    text: str = Field(..., description="Narration voiceover line")
    duration_sec: float = Field(..., description="Duration in seconds (4.0s - 8.0s)")
    word_count: int = Field(..., description="Total words in narration line")
    visual_prompt: str = Field(..., description="Visual director description of the shot")
    camera_scale: str = Field("Wide", description="Shot scale: Wide, Medium, Closeup, Detail")
    virtual_reframe: Optional[str] = Field(None, description="Virtual camera re-framing: center_zoom, pan_left_right, top_closeup, flip_slowmo")
    keywords: SceneKeyword = Field(default_factory=SceneKeyword, description="Sourcing queries")
    sfx_cue: str = Field("", description="Sound effect cue tag, e.g., creak, alarm, swoosh")
    camera_angle: str = Field("Wide", description="Camera angle or lens description")
    preferred_vault: str = Field("douyin", description="Primary vault for footage: douyin, bilibili, stock, archive_org")


class Chapter(BaseModel):
    """Chapter model containing up to 15 atomic scenes."""
    chapter_index: int = Field(..., description="Chapter index, 1-indexed")
    title: str = Field(..., description="Chapter title")
    scenes: List[Scene] = Field(default_factory=list, description="List of atomic scenes")


class Screenplay(BaseModel):
    """Master Screenplay JSON representation."""
    title: str = Field(..., description="Working project title")
    topic: str = Field(..., description="Input subject / investigation topic")
    skill_id: str = Field(..., description="Skill niche identifier")
    total_duration_sec: float = Field(0.0, description="Sum of all scene durations in seconds")
    total_words: int = Field(0, description="Total words across all scenes")
    chapters: List[Chapter] = Field(default_factory=list, description="Ordered chapters")

    @property
    def all_scenes(self) -> List[Scene]:
        scenes: List[Scene] = []
        for ch in self.chapters:
            scenes.extend(ch.scenes)
        return scenes


class SEOPackage(BaseModel):
    """SEO & Thumbnail package conforming to Counterpoint Law."""
    titles: List[str] = Field(default_factory=list, description="3 rational title options")
    description: str = Field("", description="Optimized YouTube video description")
    hashtags: List[str] = Field(default_factory=list, description="SEO hashtags")
    timestamps: List[str] = Field(default_factory=list, description="Chapter timestamps (e.g. 00:00 - Mở đầu)")
    thumbnail_badge: str = Field("", description="Short emotional badge for thumbnail card")
    thumbnail_hook: str = Field("", description="Emotional 3-5 word hook for thumbnail canvas")
    thumbnail_prompt: str = Field("", description="Emotional prompt for thumbnail generation")
    counterpoint_notes: str = Field("", description="Rationale explaining Title vs Thumbnail contrast")


# --- LLM Adapter Interfaces ---

class BaseLLMAdapter(abc.ABC):
    """Abstract interface for LLM calls (REQ-B1-01)."""

    @abc.abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generates text from a given prompt and system instruction."""
        pass


class GeminiFlashAdapter(BaseLLMAdapter):
    """
    Adapter for Google Gemini 2.0 Flash API (REQ-B1-01).
    Leverages environment variables GEMINI_API_KEY or UserSettings.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gemini-2.0-flash",
    ) -> None:
        self.api_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key:
            raise ValueError("Chưa cấu hình Gemini API Key trong Cài đặt hoặc file .env.")

        try:
            import httpx
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt}]}
                ],
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 4096},
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    raise RuntimeError("Gemini API trả về kết quả rỗng.")
                else:
                    err_msg = f"Gemini API lỗi (Mã {resp.status_code}): {resp.text}"
                    logger.error(err_msg)
                    raise RuntimeError(err_msg)
        except Exception as exc:
            logger.error("Lỗi gọi Gemini API: %s", exc)
            raise RuntimeError(f"Lỗi gọi Gemini API: {exc}") from exc


class NineRouterAdapter(BaseLLMAdapter):
    """
    Adapter for 9router OpenAI-compatible API gateway (REQ-B1-01).
    Routes requests to providers like Antigravity, OpenAI Codex, Claude, Gemini.
    Connects to {base_url}/chat/completions with Bearer authorization.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "antigravity/claude-3-5-sonnet",
    ) -> None:
        self.api_key = api_key if api_key is not None else (os.getenv("NINEROUTER_API_KEY") or os.getenv("NINE_ROUTER_API_KEY", ""))
        self.base_url = (base_url or os.getenv("NINEROUTER_BASE_URL") or "http://localhost:20128/v1").rstrip("/")
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key:
            raise ValueError(
                "Chưa cấu hình 9Router API Key trong Cài đặt! Vui lòng vào trang Cài đặt để nhập API Key và chọn mô hình."
            )

        try:
            import httpx
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 4096,
                "stream": False,
            }
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    raw_text = resp.text.strip()
                    if not raw_text:
                        raise RuntimeError("9Router trả về kết quả rỗng.")

                    # Handle Server-Sent Events stream if returned (text/event-stream or 'data: {')
                    if "text/event-stream" in resp.headers.get("content-type", "") or raw_text.startswith("data:"):
                        chunks = []
                        for line in raw_text.splitlines():
                            line = line.strip()
                            if line.startswith("data:"):
                                json_str = line[5:].strip()
                                if json_str == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(json_str)
                                    choices = chunk_data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            chunks.append(content)
                                except Exception:
                                    continue
                        if chunks:
                            return "".join(chunks)

                    # Standard OpenAI JSON response
                    try:
                        data = resp.json()
                    except Exception as json_err:
                        raise RuntimeError(f"9Router không trả về định dạng JSON hợp lệ: {raw_text[:200]}") from json_err

                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            return content
                    raise RuntimeError("9Router không trả về nội dung tạo kịch bản.")
                else:
                    err_msg = f"9Router API lỗi (Mã {resp.status_code}): {resp.text}"
                    logger.error(err_msg)
                    raise RuntimeError(err_msg)
        except Exception as exc:
            logger.error("Lỗi kết nối 9Router API: %s", exc)
            raise RuntimeError(f"Không thể kết nối đến 9Router tại {self.base_url}: {exc}") from exc


def create_default_llm_adapter() -> BaseLLMAdapter:
    """Factory creating configured LLM adapter based on settings.json and env vars."""
    try:
        from autovideo.core.settings import SettingsManager
        sm = SettingsManager()
        s = sm.load_settings()
        if s.llm_provider == "9router":
            key = s.ninerouter_api_key or os.getenv("NINEROUTER_API_KEY") or os.getenv("NINE_ROUTER_API_KEY", "")
            base = s.ninerouter_base_url or os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1")
            model = s.llm_model or "antigravity/claude-3-5-sonnet"
            return NineRouterAdapter(api_key=key, base_url=base, model=model)
        elif s.llm_provider == "gemini":
            key = s.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
            model = s.llm_model or "gemini-2.0-flash"
            return GeminiFlashAdapter(api_key=key, model=model)
        elif s.llm_provider == "mock":
            raise ValueError("Chế độ 'mock' không khả dụng trong môi trường sản xuất. Vui lòng chọn '9router' hoặc 'gemini' trong Cài Đặt.")
    except Exception as exc:
        logger.warning("Could not read settings for default LLM adapter: %s", exc)

    nr_key = os.getenv("NINEROUTER_API_KEY") or os.getenv("NINE_ROUTER_API_KEY")
    nr_base = os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1")
    if nr_key:
        return NineRouterAdapter(api_key=nr_key, base_url=nr_base)

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        return GeminiFlashAdapter(api_key=gemini_key)

    return NineRouterAdapter(api_key="", base_url="http://localhost:20128/v1")


def parse_scenes_payload(raw_response: str, topic: str = "") -> List[Dict[str, Any]]:
    """
    Robustly extracts list of scene dictionaries from JSON or Markdown LLM responses.
    Fail-fast: raises ValueError if no valid JSON scene array can be parsed.
    """
    cleaned = raw_response.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return data
        if isinstance(data, dict) and "scenes" in data and isinstance(data["scenes"], list):
            return data["scenes"]
    except Exception:
        pass

    # 2. Markdown fenced JSON block
    match = re.search(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 3. Any bracketed JSON array in text with trailing comma auto-repair
    match_any = re.search(r"(\[\s*\{.*\}\s*\])", cleaned, re.DOTALL)
    if match_any:
        raw_json_str = match_any.group(1)
        try:
            return json.loads(raw_json_str)
        except Exception:
            # Auto-repair trailing commas before closing braces/brackets
            try:
                repaired = re.sub(r",\s*([\]\}])", r"\1", raw_json_str)
                return json.loads(repaired)
            except Exception:
                pass

    # Fail fast: do NOT inject canned or mock scenes!
    snippet = cleaned[:300] + ("..." if len(cleaned) > 300 else "")
    raise ValueError(
        f"Mô hình AI không trả về danh sách phân cảnh hợp lệ ở định dạng mảng JSON.\n"
        f"Phản hồi thực tế từ mô hình:\n{snippet}"
    )


def parse_seo_payload(raw_response: str, topic: str = "") -> Dict[str, Any]:
    """
    Extracts SEO dictionary from JSON or Markdown response.
    Fail-fast: raises ValueError if no valid JSON SEO object can be parsed.
    """
    cleaned = raw_response.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and ("titles" in data or "description" in data):
            return data
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    match_any = re.search(r"(\{\s*\"titles\".*?\})", cleaned, re.DOTALL)
    if match_any:
        raw_json_str = match_any.group(1)
        try:
            return json.loads(raw_json_str)
        except Exception:
            # Auto-repair trailing commas
            try:
                repaired = re.sub(r",\s*([\]\}])", r"\1", raw_json_str)
                return json.loads(repaired)
            except Exception:
                pass

    # Fail fast: do NOT inject canned or mock SEO!
    snippet = cleaned[:300] + ("..." if len(cleaned) > 300 else "")
    raise ValueError(
        f"Mô hình AI không trả về gói SEO hợp lệ ở định dạng JSON.\n"
        f"Phản hồi thực tế từ mô hình:\n{snippet}"
    )


# --- Master Pipeline Orchestrator ---

class ScriptwritingPipeline:
    """
    Orchestrates the 7-agent scriptwriting brain, Anti-AI linter,
    and Word Budget validation to generate Master Plan screenplay and SEO package.
    """

    def __init__(
        self,
        adapter: Optional[BaseLLMAdapter] = None,
        linter: Optional[AntiAILinter] = None,
        budget_validator: Optional[WordBudgetValidator] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        self.adapter = adapter or create_default_llm_adapter()
        self.linter = linter or AntiAILinter()
        self.budget_validator = budget_validator or WordBudgetValidator()
        self.compiler = PromptCompiler()
        self.skill_registry = skill_registry or SkillRegistry()

    def generate_screenplay(
        self,
        topic: str,
        skill_id: str = "nature-wildlife-survival",
        target_scenes: int = 15,
        target_duration_min: Optional[float] = None,
    ) -> Tuple[Screenplay, SEOPackage]:
        """
        Runs the end-to-end pipeline:
        1. Compiles architect & voice prompts.
        2. Calls LLM adapter to draft scenes and SEO package.
        3. Parses output into Screenplay and SEOPackage objects.
        4. Runs AntiAILinter and WordBudgetValidator quality gates.
        """
        dur_min = target_duration_min if target_duration_min is not None else round(target_scenes / 7.5, 1)

        # Compile active skill guidance from SkillRegistry
        creative_guidance = ""
        skill_display_name = skill_id
        skill_badge = "TIÊU ĐIỂM"
        try:
            skill_obj = self.skill_registry.get_skill(skill_id)
            skill_display_name = skill_obj.name
            skill_badge = skill_obj.badge
            creative_guidance = self.skill_registry.compile(
                [skill_id],
                hooks={"script.plan", "script.rewrite", "scene.split", "prompt.image", "prompt.video"},
            )
        except Exception as exc:
            logger.info("Skill '%s' not loaded from disk registry: %s", skill_id, exc)

        # Step 1: Draft scenes (Single-Turn for <= 30 scenes, Multi-Act Batching for > 30 scenes)
        if target_scenes <= 30:
            scenes_prompt = self.compiler.build_architect_prompt(
                topic=topic,
                skill_name=skill_display_name,
                target_duration_min=dur_min,
                target_scenes=target_scenes,
                chapter_index=1,
                total_chapters=1,
                creative_guidance=creative_guidance,
            )
            raw_scenes_response = self.adapter.generate(scenes_prompt)
            scenes_raw = parse_scenes_payload(raw_scenes_response, topic)
        else:
            num_chapters = max(2, (target_scenes + 19) // 20)
            scenes_per_ch = max(10, target_scenes // num_chapters)
            scenes_raw = []
            rolling_context = ""
            for ch in range(1, num_chapters + 1):
                ch_target = scenes_per_ch if ch < num_chapters else (target_scenes - len(scenes_raw))
                ch_prompt = self.compiler.build_architect_prompt(
                    topic=topic,
                    skill_name=skill_display_name,
                    target_duration_min=round(dur_min / num_chapters, 1),
                    target_scenes=ch_target,
                    chapter_index=ch,
                    total_chapters=num_chapters,
                    creative_guidance=creative_guidance,
                )
                if rolling_context:
                    ch_prompt += (
                        f"\n\nBỐI CẢNH TIẾP NỐI TỪ HỒI TRƯỚC (Hồi {ch-1}):\n"
                        f"\"{rolling_context}\"\n"
                        f"HÃY VIẾT TIẾP DIỄN BIẾN MỚI CỦA HỒI {ch} (BẮT ĐẦU ĐÁNH SỐ TỪ SCENE_{len(scenes_raw)+1:03d}, TUYỆT ĐỐI KHÔNG VIẾT LẠI MỞ ĐẦU):"
                    )

                raw_ch_res = self.adapter.generate(ch_prompt)
                ch_scenes = parse_scenes_payload(raw_ch_res, topic)
                for s in ch_scenes:
                    s["chapter_index"] = ch
                scenes_raw.extend(ch_scenes)
                if ch_scenes:
                    rolling_context = " ".join([s.get("text", "") for s in ch_scenes[-2:]])

        # Assemble scenes into chapters
        scenes: List[Scene] = []
        for idx, item in enumerate(scenes_raw, start=1):
            # Calculate word count accurately
            text = item.get("text", "").strip()
            if text and not any(text.endswith(p) for p in (".", "!", "?", "…", "...")):
                text += "."
            word_count = len(text.split())

            dur = compute_compliant_duration(word_count, item.get("duration_sec"))

            kw_data = item.get("keywords", {})
            kw = SceneKeyword(
                vi=kw_data.get("vi", []),
                en=kw_data.get("en", []),
                zh=kw_data.get("zh", []),
            )

            sc = Scene(
                scene_id=f"SCENE_{idx:03d}",
                chapter_index=item.get("chapter_index", 1),
                cluster_id=item.get("cluster_id", f"cluster_{((idx-1)//4)+1:02d}"),
                environment_id=item.get("environment_id", "default_setting"),
                text=text,
                duration_sec=dur,
                word_count=word_count,
                visual_prompt=item.get("visual_prompt", ""),
                camera_scale=item.get("camera_scale", "Wide"),
                virtual_reframe=item.get("virtual_reframe", None),
                keywords=kw,
                sfx_cue=item.get("sfx_cue", ""),
                camera_angle=item.get("camera_angle", "Wide"),
                preferred_vault=item.get("preferred_vault", "stock"),
            )
            scenes.append(sc)

        # Partition into chapters
        chapters_dict: Dict[int, List[Scene]] = {}
        for sc in scenes:
            chapters_dict.setdefault(sc.chapter_index, []).append(sc)

        chapters: List[Chapter] = []
        for ch_idx, ch_scenes in sorted(chapters_dict.items()):
            ch_first_words = ch_scenes[0].text[:35].strip() if ch_scenes else f"Hồi {ch_idx}"
            chapters.append(
                Chapter(
                    chapter_index=ch_idx,
                    title=f"Hồi {ch_idx}: {ch_first_words}..." if ch_idx > 1 else f"Hồi 1: {ch_first_words}...",
                    scenes=ch_scenes,
                )
            )

        total_dur = sum(s.duration_sec for s in scenes)
        total_words = sum(s.word_count for s in scenes)

        screenplay = Screenplay(
            title=f"{skill_display_name}: {topic}",
            topic=topic,
            skill_id=skill_id,
            total_duration_sec=round(total_dur, 2),
            total_words=total_words,
            chapters=chapters,
        )

        # Step 2: Draft SEO & Counterpoint Package using Skill SEO guidance
        seo_guidance = ""
        try:
            seo_guidance = self.skill_registry.compile([skill_id], hooks={"prompt.seo", "prompt.thumbnail"})
        except Exception:
            pass

        seo_prompt = self.compiler.build_seo_prompt(
            topic=topic,
            screenplay_summary=f"{len(scenes)} cảnh phóng sự ({total_dur:.1f}s)",
            creative_guidance=seo_guidance,
        )
        raw_seo_response = self.adapter.generate(seo_prompt)
        seo_raw = parse_seo_payload(raw_seo_response, topic)

        # Validate required fields from LLM response
        titles = seo_raw.get("titles")
        if not titles or not isinstance(titles, list) or len(titles) == 0:
            raise ValueError(
                f"Mô hình AI không trả về danh sách tiêu đề ('titles') trong gói SEO cho chủ đề '{topic}'."
            )

        description = seo_raw.get("description")
        if not description or not str(description).strip():
            raise ValueError(
                f"Mô hình AI không trả về mô tả ('description') trong gói SEO cho chủ đề '{topic}'."
            )

        seo_package = SEOPackage(
            titles=[str(t).strip() for t in titles],
            description=str(description).strip(),
            hashtags=seo_raw.get("hashtags", []),
            timestamps=seo_raw.get("timestamps", ["00:00 - Mở đầu"]),
            thumbnail_badge=str(seo_raw.get("thumbnail_badge") or skill_badge).strip(),
            thumbnail_hook=str(seo_raw.get("thumbnail_hook") or titles[0].split(":")[0][:25]).strip(),
            thumbnail_prompt=str(seo_raw.get("thumbnail_prompt") or f"Dramatic cinematic documentary thumbnail of {topic}").strip(),
            counterpoint_notes=str(seo_raw.get("counterpoint_notes") or "").strip(),
        )

        # Step 3: Run Quality Gate Checks
        self.verify_quality_gates(screenplay)

        return screenplay, seo_package

    def verify_quality_gates(self, screenplay: Screenplay) -> None:
        """
        Validates screenplay against Gate 2 (Anti-AI & Burstiness) and Gate 3 (Word Budget).
        Raises ValueError if required constraints fail.
        """
        all_text = " ".join(s.text for s in screenplay.all_scenes)

        # 1. Anti-AI and Burstiness check (Non-blocking: static blacklist retired)
        lint_res = self.linter.lint_text(all_text)
        if lint_res.banned_matches:
            logger.info("Anti-AI Linter notice (non-blocking): %s", lint_res.banned_matches)
        if not lint_res.passed:
            logger.info("Anti-AI Linter nhịp điệu (Burstiness notice): %s", lint_res.violations)

        # 2. Word Budget auto-alignment and punctuation check
        for s in screenplay.all_scenes:
            s.duration_sec = compute_compliant_duration(s.word_count, s.duration_sec)
        screenplay.total_duration_sec = round(sum(s.duration_sec for s in screenplay.all_scenes), 2)

        scene_tuples = [(s.text, s.duration_sec) for s in screenplay.all_scenes]
        valid, violations = self.budget_validator.validate_scenes(scene_tuples)
        if not valid:
            raise ValueError(
                f"Word Budget Quality Check Failed: {violations}"
            )

    def export_artifacts(
        self,
        screenplay: Screenplay,
        seo: SEOPackage,
        output_dir: Path | str,
    ) -> Tuple[Path, Path]:
        """
        Exports the two standardized Master Plan files (REQ-B1-04):
        1. screenplay.json: Full chapter and scene layout.
        2. seo.md: YouTube metadata, hashtags, timestamps, and thumbnail concept.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 1. Export screenplay.json
        screenplay_path = out_path / "screenplay.json"
        screenplay_dict = screenplay.model_dump()
        with open(screenplay_path, "w", encoding="utf-8") as f:
            json.dump(screenplay_dict, f, ensure_ascii=False, indent=2)

        # 2. Export seo.md
        seo_path = out_path / "seo.md"
        seo_lines = [
            f"# GÓI TỐI ƯU HÓA SEO & THUMBNAIL (REQ-B1-04)",
            f"",
            f"**Chủ Đề:** {screenplay.topic}  ",
            f"**Skill Niche:** `{screenplay.skill_id}`  ",
            f"**Tổng Thời Lượng Dự Kiến:** {screenplay.total_duration_sec}s (~{round(screenplay.total_duration_sec/60, 1)} phút)  ",
            f"**Tổng Số Cảnh:** {len(screenplay.all_scenes)} phân cảnh  ",
            f"",
            f"---",
            f"",
            f"## 1. Phương Án Tiêu Đề YouTube (50 - 70 ký tự, dồn từ khóa chính vào 35 ký tự đầu)",
            f"",
        ]
        for idx, title in enumerate(seo.titles, 1):
            seo_lines.append(f"{idx}. **{title}** ({len(title)} ký tự)")

        seo_lines.extend([
            f"",
            f"---",
            f"",
            f"## 2. Mô Tả Video Chuẩn SEO",
            f"",
            f"```markdown",
            seo.description,
            f"```",
            f"",
            f"---",
            f"",
            f"## 3. Mốc Phân Chương (Timestamps)",
            f"",
        ])
        for ts in seo.timestamps:
            seo_lines.append(f"- `{ts}`")

        seo_lines.extend([
            f"",
            f"---",
            f"",
            f"## 4. Danh Sách Thẻ (Hashtags)",
            f"",
            " ".join(seo.hashtags),
            f"",
            f"---",
            f"",
            f"## 5. Ý Niệm Thumbnail Đối Nghịch (Counterpoint Thumbnail Prompt)",
            f"",
            f"> **Prompt AI Sinh Ảnh (Nano Banana 2 / Midjourney / FLUX):**",
            f"> `{seo.thumbnail_prompt}`",
            f"",
            f"---",
            f"",
            f"## 6. Ghi Chú Chiến Lược Song Tấu (Counterpoint Rationale)",
            f"",
            seo.counterpoint_notes,
            f"",
        ])

        with open(seo_path, "w", encoding="utf-8") as f:
            f.write("\n".join(seo_lines))

        return screenplay_path, seo_path
