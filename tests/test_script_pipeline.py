"""
Comprehensive Unit Tests for Multi-Agent Scriptwriting Brain (WU-03).
Covers:
- AntiAILinter: 35 banned patterns, sentence splitting, burstiness Cv, consecutive length checks.
- WordBudgetValidator: scene bounds (14-24, 25-35), terminal punctuation, duration estimation.
- PersonaRegistry & PromptCompiler: 7 personas, Cold Open 30s, Counterpoint Law.
- Screenplay & SEOPackage: Pydantic schemas, MockLLMAdapter, pipeline generation, artifact export.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from autovideo.script.anti_ai_linter import AntiAILinter, BANNED_PATTERNS_35, LintResult
from autovideo.script.word_budget import (
    WordBudgetValidator,
    calculate_scene_budget,
    estimate_duration,
)
from autovideo.script.prompts import (
    PersonaRegistry,
    PromptCompiler,
    COLD_OPEN_RULES,
    COUNTERPOINT_RULES,
)
from autovideo.script.pipeline import (
    ScriptwritingPipeline,
    Screenplay,
    Chapter,
    Scene,
    SceneKeyword,
    SEOPackage,
)
from tests.mocks.mock_llm import MockLLMAdapter


# ==============================================================================
# 1. Anti-AI Linter Tests
# ==============================================================================

def test_banned_patterns_count():
    """Verify static banned patterns list is retired (empty)."""
    assert len(BANNED_PATTERNS_35) == 0


@pytest.mark.parametrize(
    "phrase",
    [
        "bức tranh toàn cảnh",
        "minh chứng hùng hồn",
        "trong dòng chảy lịch sử",
        "hơn nữa",
        "không chỉ lợi nhuận mà còn uy tín",
        "tóm lại",
        "nhìn chung",
        "đóng vai trò quan trọng",
        "góp phần không nhỏ",
        "vô hình trung",
        "có thể thấy rằng",
        "chúng ta hãy cùng",
        "bước chuyển mình",
        "dấu ấn đậm nét",
        "bản hòa ca",
        "văn chương thường thi vị hóa",
        "từ xa xưa",
        "ngọn hải đăng",
    ],
)
def test_linter_detects_banned_patterns_when_configured(phrase: str):
    """Test that custom configured patterns are caught if explicitly provided."""
    linter = AntiAILinter(banned_patterns=[phrase])
    text = f"Sự việc này là một {phrase} về thảm họa kỹ thuật công nghiệp tại hiện trường."
    res = linter.lint_text(text)
    assert not res.passed
    assert len(res.banned_matches) > 0


def test_linter_default_has_no_static_banned_patterns():
    """Default linter has no static banned patterns, ensuring zero false-positive rejections."""
    linter = AntiAILinter()
    text = "Trên thực tế, linh cẩu đốm không chỉ săn mồi mà còn đóng vai trò quan trọng hơn nữa."
    res = linter.lint_text(text)
    assert len(res.banned_matches) == 0


def test_linter_case_insensitive_and_whitespace():
    """Linter should detect custom pattern regardless of capitalization and extra whitespace."""
    linter = AntiAILinter(banned_patterns=["bức tranh toàn cảnh"])
    text = "Đây là   BỨC   TRANH   TOÀN   CẢNH   về vụ sập kệ kho bãi."
    res = linter.lint_text(text)
    assert not res.passed
    assert any("bức tranh toàn cảnh" in m for m in res.banned_matches)


def test_linter_sentence_splitting_with_abbreviations():
    """Linter preserves abbreviations (TP.HCM, 3.5 tấn) without split errors."""
    text = "Vụ tai nạn xảy ra tại TP.HCM vào rạng sáng. Xe nâng chở 3.5 tấn hàng hóa đã va quẹt vào chân kệ."
    sentences = AntiAILinter.split_sentences(text)
    assert len(sentences) == 2
    assert "TP.HCM" in sentences[0]
    assert "3.5 tấn" in sentences[1]


def test_linter_burstiness_cv_calculation():
    """Test coefficient of variation calculation."""
    linter = AntiAILinter()
    # Identical lengths -> Cv = 0.0
    cv_zero = linter.calculate_cv([10, 10, 10, 10])
    assert cv_zero == 0.0

    # Highly varied lengths (3, 25, 4, 30, 5) -> Cv >= 0.4
    cv_high = linter.calculate_cv([3, 25, 4, 30, 5])
    assert cv_high >= 0.4


def test_linter_consecutive_lengths_violation():
    """Check violation when 3 consecutive sentences have identical or near-identical length (range <= 3)."""
    linter = AntiAILinter(consecutive_length_tolerance=3)
    # 10, 12, 11 -> range = 12 - 10 = 2 <= 3 -> Violation!
    has_violation, msgs = linter.check_consecutive_lengths([10, 12, 11, 25, 5])
    assert has_violation is True
    assert len(msgs) == 1

    # 5, 20, 8 -> range = 20 - 5 = 15 > 3 -> No violation
    has_violation2, _ = linter.check_consecutive_lengths([5, 20, 8, 30, 4])
    assert has_violation2 is False


def test_linter_clean_text_passes():
    """Text without banned clichés, high Cv, and varied lengths passes linting."""
    linter = AntiAILinter(min_cv=0.4)
    # 3 sentences: 4 words, 25 words, 5 words -> Cv > 0.4, range > 3, 0 banned words
    clean_text = (
        "Kho hàng đổ sập. "
        "Tổng tải trọng chất quá mức quy định đã tương đương với mười chiếc xe tăng đè lên bốn trụ đỡ đơn độc bằng thép mỏng. "
        "Ai phải chịu trách nhiệm?"
    )
    res = linter.lint_text(clean_text)
    assert res.passed is True
    assert res.cv >= 0.4
    assert len(res.banned_matches) == 0


# ==============================================================================
# 2. Word Budget & Pacing Tests
# ==============================================================================

def test_calculate_scene_budget():
    """Validate 4s-5s and 6s-8s word budgets."""
    min_4s, max_4s = calculate_scene_budget(4.5)
    assert (min_4s, max_4s) == (14, 24)

    min_5s, max_5s = calculate_scene_budget(5.0)
    assert (min_5s, max_5s) == (14, 24)

    min_7s, max_7s = calculate_scene_budget(7.0)
    assert (min_7s, max_7s) == (25, 35)


def test_estimate_duration():
    """Validate duration estimation at standard 2.85 wps."""
    assert estimate_duration(0) == 0.0
    # 28 words / 2.85 = ~9.82s
    dur = estimate_duration(28)
    assert 9.5 <= dur <= 10.0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Đây là câu kết thúc chuẩn.", True),
        ("Cảnh báo nguy hiểm!", True),
        ("Ai là người chịu trách nhiệm?", True),
        ("Và câu chuyện vẫn tiếp diễn…", True),
        ("Câu thoại kết thúc lơ lửng,", False),
        ("Câu này không có dấu câu", False),
        ("Kết thúc bằng dấu hai chấm:", False),
        ("Kết thúc bằng gạch nối -", False),
    ],
)
def test_terminal_punctuation_validation(text: str, expected: bool):
    """Test terminating punctuation detector."""
    assert WordBudgetValidator.has_valid_terminal_punctuation(text) == expected


def test_scene_budget_validator_bounds():
    """Test WordBudgetValidator bounds enforcement."""
    validator = WordBudgetValidator()

    # Too short for 7.0s (requires 25-35 words)
    short_text = "Hàng hóa bị đè nát hoàn toàn dưới đống sắt vụn."  # 11 words
    res_short = validator.validate_scene(short_text, duration_sec=7.0)
    assert not res_short.is_valid
    assert any("below minimum budget" in v for v in res_short.violations)

    # Valid scene (28 words for 7.0s)
    valid_text = (
        "Sai lầm sơ đẳng. "
        "Tổng tải trọng chất quá mức quy định đã tương đương với mười chiếc xe tăng đè nặng lên bốn trụ đỡ đơn độc."
    )
    res_valid = validator.validate_scene(valid_text, duration_sec=7.0)
    assert res_valid.is_valid is True
    assert res_valid.word_count == 28
    assert res_valid.min_budget == 25
    assert res_valid.max_budget == 35


# ==============================================================================
# 3. Prompts & Persona System Tests
# ==============================================================================

def test_persona_registry_retrieval():
    """Verify all personas are accessible and contain expected roles."""
    personas = PersonaRegistry.get_all_personas()
    assert len(personas) >= 7
    expected_keys = [
        "researcher",
        "architect",
        "voice_writer",
        "humanizer",
        "scene_splitter",
        "quality_gate",
        "commentator",
        "historical_storyteller",
        "nature_storyteller",
    ]
    for key in expected_keys:
        assert key in personas
        assert personas[key].agent_id == key
        assert len(personas[key].system_prompt) > 50


def test_cold_open_and_counterpoint_rules_constants():
    """Verify Cold Open 30s and Counterpoint rules contain required guidance."""
    assert "0–5 giây" in COLD_OPEN_RULES or "0-5s" in COLD_OPEN_RULES
    assert "CÚ SỐC SỐ LIỆU" in COLD_OPEN_RULES
    assert "ĐẬP TAN NGỘ NHẬN" in COLD_OPEN_RULES
    assert "LUẬN ĐỀ ĐIỀU TRA" in COLD_OPEN_RULES

    assert "50 – 70 ký tự" in COUNTERPOINT_RULES or "50-70 ký tự" in COUNTERPOINT_RULES
    assert "35 ký tự đầu" in COUNTERPOINT_RULES
    assert "KHÔNG BAO GIỜ lặp lại từ" in COUNTERPOINT_RULES


def test_prompt_compiler():
    """Test PromptCompiler produces coherent instructions."""
    compiler = PromptCompiler()
    arch_prompt = compiler.build_architect_prompt("Sự cố sập kho", "Warehouse Fails")
    assert "Sự cố sập kho" in arch_prompt
    assert "COLD OPEN" in arch_prompt

    voice_prompt = compiler.build_voice_writer_prompt("Dàn ý Hồi 1", "Sự cố sập kho")
    assert "Dàn ý Hồi 1" in voice_prompt
    assert "4s-8s" in voice_prompt

    seo_prompt = compiler.build_seo_prompt("Sự cố sập kho", "Sập kệ", "15 cảnh")
    assert "COUNTERPOINT" in seo_prompt or "SONG TẤU" in seo_prompt


# ==============================================================================
# 4. Pipeline Orchestrator & Screenplay Schema Tests
# ==============================================================================

def test_screenplay_pydantic_schema():
    """Verify serialization and structure of Screenplay and Scene models."""
    scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Đúng mười lăm triệu đô la hàng hóa tan thành đống đổ nát chỉ sau ba giây va chạm.",
        duration_sec=5.0,
        word_count=17,
        visual_prompt="CCTV high angle of swaying rack",
        keywords=SceneKeyword(vi=["sập kệ"], en=["rack collapse"], zh=["货架倒塌"]),
        sfx_cue="thud",
        camera_angle="Wide",
        preferred_vault="douyin",
    )
    chapter = Chapter(chapter_index=1, title="Hồi 1", scenes=[scene])
    screenplay = Screenplay(
        title="Điều Tra Sập Kệ",
        topic="Sập kệ kho hàng",
        skill_id="warehouse-fails",
        total_duration_sec=5.0,
        total_words=17,
        chapters=[chapter],
    )

    dumped = screenplay.model_dump()
    assert dumped["title"] == "Điều Tra Sập Kệ"
    assert len(dumped["chapters"]) == 1
    assert dumped["chapters"][0]["scenes"][0]["scene_id"] == "SCENE_001"
    assert screenplay.all_scenes[0].keywords.zh == ["货架倒塌"]


def test_mock_llm_adapter_screenplay_generation():
    """Verify MockLLMAdapter produces valid JSON data conforming to requirements."""
    adapter = MockLLMAdapter()
    resp = adapter.generate("CHỦ ĐỀ: Sự cố sập kho")
    scenes = json.loads(resp)
    assert len(scenes) == 15

    # Check 100% of scenes have 14 to 35 words and end with punctuation
    for idx, sc in enumerate(scenes):
        wc = len(sc["text"].split())
        assert 14 <= wc <= 35, f"Scene #{idx+1} word count {wc} out of range [14, 35]"
        assert sc["text"].strip().endswith((".", "!", "?")), f"Scene #{idx+1} missing punctuation"


def test_pipeline_generate_and_quality_gates(tmp_path: Path):
    """End-to-end test of ScriptwritingPipeline with quality gates and artifact export."""
    pipeline = ScriptwritingPipeline(adapter=MockLLMAdapter())

    screenplay, seo = pipeline.generate_screenplay(
        topic="Sự cố sập giá đỡ kho hàng triệu đô",
        skill_id="warehouse-fails",
        target_scenes=15,
    )

    # Assertions on screenplay
    assert len(screenplay.chapters) == 2
    assert len(screenplay.all_scenes) == 15
    assert screenplay.total_duration_sec > 0
    assert screenplay.total_words > 0

    # Cold open 30s check (scenes 1 to 3)
    cold_open_scenes = screenplay.all_scenes[:3]
    cold_open_dur = sum(s.duration_sec for s in cold_open_scenes)
    assert 14.0 <= cold_open_dur <= 25.0
    assert "mười lăm triệu đô" in cold_open_scenes[0].text.lower()

    # Assertions on SEO package
    assert len(seo.titles) == 3
    for title in seo.titles:
        assert 50 <= len(title) <= 75
    assert len(seo.hashtags) >= 5
    assert len(seo.timestamps) >= 3
    assert "bottom-right 20%" in seo.thumbnail_prompt.lower() or "20%" in seo.thumbnail_prompt

    # Test export artifacts
    screenplay_file, seo_file = pipeline.export_artifacts(screenplay, seo, tmp_path)
    assert screenplay_file.exists()
    assert seo_file.exists()

    # Verify exported screenplay.json
    with open(screenplay_file, "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    assert loaded_data["topic"] == "Sự cố sập giá đỡ kho hàng triệu đô"
    assert len(loaded_data["chapters"]) == 2

    # Verify exported seo.md
    seo_content = seo_file.read_text(encoding="utf-8")
    assert "# GÓI TỐI ƯU HÓA SEO & THUMBNAIL" in seo_content
    assert "Phương Án Tiêu Đề YouTube" in seo_content
    assert "Mô Tả Video Chuẩn SEO" in seo_content
    assert "Mốc Phân Chương (Timestamps)" in seo_content
    assert "Ý Niệm Thumbnail Đối Nghịch" in seo_content


def test_pipeline_quality_gate_passes_without_static_banning():
    """Verify verify_quality_gates accepts scenes containing natural transition phrases."""
    pipeline = ScriptwritingPipeline()
    scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Trên thực tế, đây là bức tranh toàn cảnh về sự cố sập kho bãi.",
        duration_sec=5.0,
        word_count=14,
        visual_prompt="test",
    )
    screenplay = Screenplay(
        title="Valid Screenplay",
        topic="Valid Topic",
        skill_id="test",
        total_duration_sec=5.0,
        total_words=14,
        chapters=[Chapter(chapter_index=1, title="Hồi 1", scenes=[scene])],
    )

    # Should not raise ValueError even with formerly blacklisted words
    pipeline.verify_quality_gates(screenplay)


def test_pipeline_quality_gate_word_budget_rejection():
    """Verify verify_quality_gates still rejects scenes violating word budget terminal punctuation requirements."""
    pipeline = ScriptwritingPipeline()
    # Create scene with non-compliant text without punctuation that validator rejects
    bad_scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Từ ngữ không dấu kết thúc",
        duration_sec=5.0,
        word_count=5,
        visual_prompt="test",
    )
    bad_screenplay = Screenplay(
        title="Bad Screenplay",
        topic="Bad Topic",
        skill_id="test",
        total_duration_sec=5.0,
        total_words=5,
        chapters=[Chapter(chapter_index=1, title="Hồi 1", scenes=[bad_scene])],
    )

    with pytest.raises(ValueError) as excinfo:
        pipeline.verify_quality_gates(bad_screenplay)
    assert "Word Budget Quality Check Failed" in str(excinfo.value)
