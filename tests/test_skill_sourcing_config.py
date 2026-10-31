"""
Unit tests for Skill-Niche Declarative Video Sourcing Configuration.
Verifies that categories, fallback search templates, and trusted channels
are completely driven by Skill manifests (skill.yaml) with zero hardcoding.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from autovideo.skills.registry import SkillRegistry
from autovideo.sourcing.engine import AssetSourcingEngine
from autovideo.sourcing.universal import UniversalDownloader


def test_all_installed_skills_have_declarative_sourcing_fields():
    """All 5 built-in skill niches define preferred/discouraged categories and fallback templates in skill.yaml."""
    registry = SkillRegistry()
    skills = registry.list_skills()
    assert len(skills) >= 5, f"Expected at least 5 skills, found {len(skills)}"

    for sk in skills:
        manifest = sk.manifest
        assert isinstance(manifest.preferred_categories, list), f"{sk.id} preferred_categories should be a list"
        assert len(manifest.preferred_categories) > 0, f"{sk.id} must define preferred_categories in skill.yaml"

        assert isinstance(manifest.discouraged_categories, list), f"{sk.id} discouraged_categories should be a list"
        assert len(manifest.discouraged_categories) > 0, f"{sk.id} must define discouraged_categories in skill.yaml"

        assert isinstance(manifest.fallback_search_templates, list), f"{sk.id} fallback_search_templates should be a list"
        assert len(manifest.fallback_search_templates) > 0, f"{sk.id} must define fallback_search_templates in skill.yaml"

        for tpl in manifest.fallback_search_templates:
            assert "{subject_anchor}" in tpl, f"Template '{tpl}' in skill '{sk.id}' must include {{subject_anchor}}"


def test_universal_scoring_driven_strictly_by_parameters(tmp_path: Path):
    """UniversalDownloader dynamically respects whatever preferred and discouraged categories are passed."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "howto_clip",
            "title": "How to sketch a spotted hyena face in pencil",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,
            "categories": ["Howto & Style"],
        },
        {
            "id": "nature_clip",
            "title": "Spotted hyena bone crushing power in savanna",
            "duration": 45.0,
            "height": 1080,
            "width": 1920,
            "categories": ["Pets & Animals", "Education"],
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "nature_clip.mp4") as mock_dl:
            # Case A: Wildlife Niche (Favors Pets & Animals, discourages Howto & Style)
            res_a = downloader.download(
                "ytsearch8:spotted hyena teeth",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                preferred_categories=["Pets & Animals", "Science & Technology"],
                discouraged_categories=["Howto & Style"],
            )
            assert res_a.video_id == "nature_clip"
            assert mock_dl.call_args[0][1] == "nature_clip"

    # Case B: Hypothetical Art/DIY Niche (Reverses preferences: Favors Howto & Style, discourages Pets & Animals)
    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "howto_clip.mp4") as mock_dl_b:
            res_b = downloader.download(
                "ytsearch8:spotted hyena sketch",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                preferred_categories=["Howto & Style"],
                discouraged_categories=["Pets & Animals"],
            )
            assert res_b.video_id == "howto_clip"
            assert mock_dl_b.call_args[0][1] == "howto_clip"


def test_asset_sourcing_engine_auto_resolves_niche_preferences(tmp_path: Path):
    """AssetSourcingEngine looks up skill preferences from registry and forwards them to universal downloader."""
    registry = SkillRegistry()
    engine = AssetSourcingEngine(skill_registry=registry)

    mock_universal_info = MagicMock(
        downloaded_path=tmp_path / "warehouse.mp4",
        duration_sec=30.0,
        extractor="youtube",
        video_id="wh_001",
        width=1920,
        height=1080,
    )

    with patch.object(engine.universal, "download", return_value=mock_universal_info) as mock_u_dl:
        res = engine.source_scene_asset(
            scene_id="SCENE_001",
            query="forklift tipping over",
            preferred_vault="universal",
            niche_id="warehouse-fails",
        )
        assert res.scene_id == "SCENE_001"
        call_kwargs = mock_u_dl.call_args[1]

        # Verify that warehouse-fails categories were resolved from skill.yaml
        assert "News & Politics" in call_kwargs.get("preferred_categories", [])
        assert "Film & Animation" in call_kwargs.get("discouraged_categories", [])


def test_fallback_search_templates_diversity_across_niches():
    """Different niches yield contextually appropriate fallback search queries."""
    registry = SkillRegistry()

    # Nature skill
    nature_sk = registry.get_skill("nature-wildlife-survival")
    anchor_nature = "spotted hyena"
    nature_fallbacks = [tpl.format(subject_anchor=anchor_nature) for tpl in nature_sk.manifest.fallback_search_templates]
    assert any("in the wild" in fb for fb in nature_fallbacks)
    assert any("wildlife documentary" in fb for fb in nature_fallbacks)

    # Warehouse fails skill
    warehouse_sk = registry.get_skill("warehouse-fails")
    anchor_warehouse = "warehouse forklift accident"
    warehouse_fallbacks = [tpl.format(subject_anchor=anchor_warehouse) for tpl in warehouse_sk.manifest.fallback_search_templates]
    assert any("cctv footage" in fb for fb in warehouse_fallbacks)
    assert not any("savanna" in fb for fb in warehouse_fallbacks)
    assert not any("in the wild" in fb for fb in warehouse_fallbacks)
