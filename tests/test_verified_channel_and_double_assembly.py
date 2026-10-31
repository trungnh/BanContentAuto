import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from autovideo.production.chapter_builder import ChapterBuilder, SceneAssets
from autovideo.sourcing.universal import UniversalDownloader
from autovideo.script.pipeline import Chapter, Scene, Screenplay


def test_category_alignment_and_fair_use():
    """Verify that Fair Use allows verified science channels, while off-topic categories (Howto & Style / Tattoos) are rejected."""
    downloader = UniversalDownloader()

    # Candidate with verified educational science channel (Real Science)
    verified_science_entry = {
        "id": "vid_science",
        "title": "The Insane Biology of: The Spotted Hyena",
        "uploader": "Real Science",
        "channel_is_verified": True,
        "categories": ["Science & Technology"],
        "duration": 60,
        "width": 1920,
        "height": 1080,
    }

    # Candidate from off-topic category (Howto & Style / Tattoo studio)
    tattoo_entry = {
        "id": "vid_tattoo",
        "title": "Custom Floral & Hyena Skull Tattoo",
        "uploader": "Snow Tattoo",
        "channel_is_verified": None,
        "categories": ["Howto & Style"],
        "duration": 60,
        "width": 1920,
        "height": 1080,
    }

    with patch.object(downloader, "get_video_info") as mock_info:
        mock_info.return_value = {"entries": [tattoo_entry, verified_science_entry]}
        with patch.object(downloader, "_download_and_verify") as mock_dl:
            mock_dl.return_value = Path("cache/raw_footage/universal_vid_science.mp4")
            res = downloader.download(
                "ytsearch2:hyena",
                enforce_duration=False,
                subject_anchor="hyena",
                preferred_categories=["Science & Technology"],
                discouraged_categories=["Howto & Style"],
            )
            # The chosen candidate must be the educational science channel, rejecting Howto & Style!
            assert res.video_id == "vid_science"


def test_subject_anchor_absence_penalty():
    """Verify that off-topic candidate (e.g. human dental clinic) is severely penalized when subject_anchor is hyena."""
    downloader = UniversalDownloader()

    dental_clinic_entry = {
        "id": "vid_dentist",
        "title": "Carnivore Diet and Teeth Health Explained",
        "uploader": "Integrated Dentalcare",
        "channel_is_verified": None,
        "duration": 60,
        "width": 1920,
        "height": 1080,
    }

    hyena_entry = {
        "id": "vid_hyena",
        "title": "Spotted Hyena chewing on bone",
        "uploader": "Safari Guide",
        "channel_is_verified": None,
        "duration": 60,
        "width": 1920,
        "height": 1080,
    }

    with patch.object(downloader, "get_video_info") as mock_info:
        mock_info.return_value = {"entries": [dental_clinic_entry, hyena_entry]}
        with patch.object(downloader, "_download_and_verify") as mock_dl:
            mock_dl.return_value = Path("cache/raw_footage/universal_vid_hyena.mp4")
            res = downloader.download(
                "ytsearch2:spotted hyena teeth",
                enforce_duration=False,
                subject_anchor="spotted hyena",
            )
            assert res.video_id == "vid_hyena"


def test_chapter_builder_preassembled_scene_bypass(tmp_path: Path):
    """Verify that when is_preassembled=True, ChapterBuilder does not re-mux and avoids 0.0s offset bug."""
    builder = ChapterBuilder()

    # Create a dummy pre-assembled scene file
    preassembled_scene = tmp_path / "scene_001_clean.mp4"
    preassembled_scene.write_bytes(b"dummy clean scene content")

    chapter = Chapter(
        chapter_index=1,
        title="Chapter 1",
        scenes=[
            Scene(
                scene_id="SCENE_001",
                chapter_index=1,
                text="Test scene text.",
                duration_sec=5.0,
                word_count=18,
                visual_prompt="Test visual prompt.",
            )
        ],
    )

    assets_map = {
        "SCENE_001": SceneAssets(
            media_path=preassembled_scene,
            is_preassembled=True,
            start_offset_sec=7.0,
        )
    }

    # Mock concat demuxer so it doesn't invoke ffmpeg
    with patch.object(builder._concat_demuxer, "concat") as mock_concat:
        with patch.object(builder, "is_chapter_part_valid", return_value=False):
            with patch.object(builder._scene_muxer, "assemble_scene") as mock_muxer:
                parts_dir = tmp_path / "parts"
                builder.build_chapter(
                    project_id="proj_test",
                    chapter=chapter,
                    asset_resolver=assets_map,
                    parts_dir=parts_dir,
                    resume=False,
                )

                # Assemble scene must NOT be called because is_preassembled=True
                mock_muxer.assert_not_called()
                # Concat must be called with the copied preassembled scene
                mock_concat.assert_called_once()
                input_paths = mock_concat.call_args.kwargs.get("input_paths") or mock_concat.call_args[1].get("input_paths")
                assert len(input_paths) == 1
                assert "scene_01_001.mp4" in str(input_paths[0])


def test_regenerate_thumbnail_api(tmp_path: Path):
    """Verify POST /api/projects/{id}/thumbnail/regenerate generates AI raw image, composite and safe zone."""
    from fastapi.testclient import TestClient
    from autovideo.api.app import create_app
    from autovideo.core.config import AppConfig
    from autovideo.coordinator import MasterPipelineCoordinator

    cfg = AppConfig()
    cfg.paths.base_dir = tmp_path
    cfg.paths.ensure_directories()
    coord = MasterPipelineCoordinator(config=cfg)
    app = create_app(config=cfg, coordinator=coord)
    client = TestClient(app)

    # Initialize a test project
    p = coord.create_project(topic="Linh cẩu đốm săn mồi", skill_id="nature-wildlife-survival", target_duration_min=15, project_id="proj_thumb_test")
    p.seo_package = {
        "thumbnail_prompt": "spotted hyena eating",
        "thumbnail_hook": "HOOK CỰC CĂNG",
        "thumbnail_badge": "SINH TỒN",
    }

    with patch("autovideo.publisher.image_client.NineRouterImageClient.generate_image") as mock_gen_img:
        def create_dummy_raw(prompt, output_path, model=None):
            from PIL import Image
            img = Image.new("RGB", (1280, 720), color=(100, 150, 200))
            img.save(output_path)
        mock_gen_img.side_effect = create_dummy_raw

        resp = client.post("/api/projects/proj_thumb_test/thumbnail/regenerate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "/preview/thumbnail" in data["thumbnail_url"]

        p_dir = cfg.paths.get_project_render_dir("proj_thumb_test")
        assert (p_dir / "thumbnail_raw.jpg").exists()
        assert (p_dir / "thumbnail.jpg").exists()
        assert (p_dir / "thumbnail_safe_zone_preview.jpg").exists()
