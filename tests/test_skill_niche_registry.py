"""
Test suite for Skill Niche System (SPEC-AVF-SKILL-NICHE-V1).
Validates manifest validation, registry lifecycle, hook compilation,
zero-hardcoding SEO and scriptwriting integration, and /api/skills endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.publisher.seo_packager import SEOPackager
from autovideo.script.pipeline import ScriptwritingPipeline
from tests.mocks.mock_llm import MockLLMAdapter
from autovideo.skills.manifest import ALLOWED_HOOKS, SkillManifest
from autovideo.skills.registry import SkillRegistry


def test_allowed_hooks_definition():
    """Verify that all 12 standardized hooks from SPEC-AVF-SKILL-NICHE-V1 are registered."""
    assert len(ALLOWED_HOOKS) == 12
    assert "script.plan" in ALLOWED_HOOKS
    assert "script.rewrite" in ALLOWED_HOOKS
    assert "scene.split" in ALLOWED_HOOKS
    assert "prompt.image" in ALLOWED_HOOKS
    assert "prompt.video" in ALLOWED_HOOKS
    assert "prompt.thumbnail" in ALLOWED_HOOKS
    assert "prompt.seo" in ALLOWED_HOOKS
    assert "voice.direction" in ALLOWED_HOOKS


def test_manifest_validation_valid():
    """Test valid skill manifest creation."""
    m = SkillManifest(
        schema_version=1,
        id="test-niche-skill",
        name="Test Niche Skill",
        style_name="Test Cinematic Style",
        badge="Test · Badge",
        version="1.0.0",
        description="Test description for niche.",
        hooks={
            "script.plan": "prompts/script.md",
            "prompt.seo": "prompts/seo.md",
        },
    )
    assert m.id == "test-niche-skill"
    assert m.badge == "Test · Badge"
    assert "script.plan" in m.hooks


def test_manifest_validation_path_traversal_rejection():
    """Ensure path traversal attempts in hooks are blocked by schema validation."""
    with pytest.raises(ValueError, match="Path traversal detected"):
        SkillManifest(
            schema_version=1,
            id="bad-skill",
            name="Bad Skill",
            style_name="Bad Style",
            hooks={"script.plan": "../secret/script.md"},
        )


def test_manifest_invalid_hook_rejection():
    """Ensure non-standard hooks are rejected."""
    with pytest.raises(ValueError, match="not in ALLOWED_HOOKS"):
        SkillManifest(
            schema_version=1,
            id="bad-hook-skill",
            name="Bad Hook",
            style_name="Bad Style",
            hooks={"arbitrary.hook": "prompts/bad.md"},
        )


def test_skill_registry_list_and_load():
    """Test SkillRegistry loads installed skills from disk."""
    reg = SkillRegistry()
    skills = reg.list_skills()
    assert len(skills) >= 5

    skill_ids = [s.id for s in skills]
    assert "nature-wildlife-survival" in skill_ids
    assert "historical-mysteries" in skill_ids
    assert "warehouse-fails" in skill_ids
    assert "military-microhistory" in skill_ids
    assert "extreme-weather" in skill_ids


def test_nature_wildlife_skill_integrity():
    """Verify nature-wildlife-survival skill contains required playbook and hooks."""
    reg = SkillRegistry()
    skill = reg.get_skill("nature-wildlife-survival")
    assert skill.manifest.badge == "Thiên Nhiên · Sinh Tồn & Sách Đỏ"
    assert "David Attenborough" in skill.playbook_text or "BBC Earth" in skill.playbook_text

    # Read individual hooks
    script_plan = skill.read_hook_content("script.plan")
    assert script_plan is not None
    assert "Cấu trúc 5 Hồi Điện Ảnh" in script_plan

    prompt_seo = skill.read_hook_content("prompt.seo")
    assert prompt_seo is not None
    assert "Bản Án Tuyệt Chủng" in prompt_seo or "Tiêu đề" in prompt_seo


def test_skill_compile_and_extract_hook():
    """Test compiling hooks across a skill and extracting single hook block."""
    reg = SkillRegistry()
    compiled = reg.compile(["nature-wildlife-survival"], hooks={"script.plan", "prompt.seo"})
    assert "# Skill: Nature & Wildlife Survival Documentary" in compiled
    assert "## Hook: script.plan" in compiled
    assert "## Hook: prompt.seo" in compiled

    extracted_seo = reg.extract_hook_content(compiled, "prompt.seo")
    assert "Hook: prompt.seo" not in extracted_seo
    assert "Tiêu đề" in extracted_seo or "Hổ Tasmania" in extracted_seo


def test_scriptwriting_pipeline_with_nature_skill():
    """Verify ScriptwritingPipeline accepts nature skill and produces non-hardcoded output."""
    pipeline = ScriptwritingPipeline(adapter=MockLLMAdapter())
    screenplay, seo_pkg = pipeline.generate_screenplay(
        topic="Benjamin - Con hổ Tasmania cuối cùng",
        skill_id="nature-wildlife-survival",
        target_scenes=15,
    )
    assert screenplay.skill_id == "nature-wildlife-survival"
    assert "Nature & Wildlife Survival" in screenplay.title
    assert len(screenplay.chapters) >= 1
    assert len(screenplay.all_scenes) == 15

    # Check SEO package uses nature theme, NOT 'Hồ sơ kín'
    assert len(seo_pkg.titles) >= 1
    first_title = seo_pkg.titles[0]
    assert "Hồ sơ kín" not in first_title
    assert "Đại án điều tra" not in first_title
    assert seo_pkg.thumbnail_badge in ("TUYỆT CHỦNG", "Thiên Nhiên · Sinh Tồn & Sách Đỏ", "TIÊU ĐIỂM")


def test_seo_packager_with_llm_input():
    """Verify SEOPackager prioritizes LLM-generated titles and descriptions over static fallbacks."""
    packager = SEOPackager()
    custom_seo = {
        "titles": [
            "Hổ Tasmania: Bản Án Tuyệt Chủng Của Một Tuyệt Tác Tiến Hóa",
            "Cái Chết Cô Độc Của Con Hổ Cuối Cùng Và Lời Thức Tỉnh Muộn Màng",
            "Hồi Sinh Loài Tuyệt Chủng: Khoa Học ADN Liệu Có Thể Đảo Ngược?",
        ],
        "description": "Phim tài liệu chuyên sâu về số phận bi tráng của loài Thylacine.",
        "tags": ["Hổ Tasmania", "Thylacine", "Tuyệt chủng", "Sách Đỏ"],
        "hashtags": ["#TasmanianTiger", "#TuyetChung"],
        "thumbnail_badge": "TUYỆT CHỦNG",
        "thumbnail_hook": "CON THÚ CUỐI CÙNG",
    }
    chapters = [{"title": "Mở đầu", "duration_sec": 60.0}, {"title": "Khám phá", "duration_sec": 120.0}]

    pkg = packager.generate_package(
        project_id="test_nature_01",
        topic="Hổ Tasmania",
        chapters=chapters,
        seo_input=custom_seo,
    )

    assert pkg.titles[0] == "Hổ Tasmania: Bản Án Tuyệt Chủng Của Một Tuyệt Tác Tiến Hóa"
    assert "Hồ sơ kín" not in pkg.titles[0]
    assert pkg.thumbnail_badge == "TUYỆT CHỦNG"
    assert pkg.thumbnail_hook == "CON THÚ CUỐI CÙNG"
    assert "Phim tài liệu chuyên sâu về số phận bi tráng" in pkg.description
    assert "00:00 Mở đầu" in pkg.description


def test_api_skills_endpoint():
    """Verify GET /api/skills endpoint returns all installed skills."""
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/skills")
    assert res.status_code == 200
    data = res.json()
    assert "skills" in data
    skills = data["skills"]
    assert len(skills) >= 5

    nature = next((s for s in skills if s["id"] == "nature-wildlife-survival"), None)
    assert nature is not None
    assert nature["badge"] == "Thiên Nhiên · Sinh Tồn & Sách Đỏ"
    assert "Phóng sự hoang dã" in nature["style_name"]
