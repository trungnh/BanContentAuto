"""
Unit tests for Sourcing Precision: Subject Anchoring, Smart Negative Filtering, and Offset Trimming.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autovideo.coordinator import MasterPipelineCoordinator
from autovideo.sourcing.engine import AssetSourcingEngine
from autovideo.sourcing.universal import DEFAULT_NEGATIVE_TERMS, UniversalDownloader


def test_coordinator_extracts_subject_anchor():
    """Coordinator correctly extracts English subject anchors from diverse Vietnamese and bilingual topics."""
    coord = MasterPipelineCoordinator.__new__(MasterPipelineCoordinator)

    # Animals
    assert coord._extract_subject_anchor("Lửng mật (Honey Badger): Sinh vật bất tử", "nature-wildlife-survival") == "honey badger"
    assert coord._extract_subject_anchor("Hổ Tasmania: Loài thú có túi đã tuyệt chủng", "nature-wildlife-survival") == "tasmanian tiger thylacine"
    assert coord._extract_subject_anchor("Cuộc chiến sinh tồn của bầy sư tử và linh cẩu", "nature-wildlife-survival") == "african lion"
    assert coord._extract_subject_anchor("Rắn hổ mang chúa Kalahari", "nature-wildlife-survival") == "king cobra snake"

    # History
    assert coord._extract_subject_anchor("Bí mật lăng mộ Chu Nguyên Chương thời Minh", "historical-mysteries") == "hongwu emperor ming dynasty"
    assert coord._extract_subject_anchor("Bí ẩn xây dựng Kim Tự Tháp Giza", "historical-mysteries") == "egyptian pyramid ancient cairo"

    # Warehouse fails
    assert coord._extract_subject_anchor("Sập kệ kho hàng 15 triệu USD", "warehouse-fails") == "warehouse forklift accident"


def test_universal_smart_ranking_rejects_negative_terms(tmp_path: Path):
    """UniversalDownloader rejects news, movie clips, and cartoons in favor of clean documentary footage."""
    downloader = UniversalDownloader()

    fake_entries = [
        {"id": "swns_news", "title": "SWNS News: Villagers gather around radio tower", "duration": 45.0, "height": 1080, "width": 1920},
        {"id": "vtc14_tv", "title": "Bản tin Cuộc sống 24h VTC14 Cấp cứu", "duration": 40.0, "height": 1080, "width": 1920},
        {"id": "predator_movie", "title": "Predator (1987) Fandango Movieclips", "duration": 50.0, "height": 1080, "width": 1920},
        {"id": "clean_wildlife", "title": "Honey Badger fearless wildlife encounter in Kalahari", "duration": 35.0, "height": 720, "width": 1280, "uploader": "Nat Geo Wild"},
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "clean_wildlife.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:nature survivor",
                output_dir=tmp_path,
                subject_anchor="honey badger",
                negative_terms=DEFAULT_NEGATIVE_TERMS,
            )
            assert res.video_id == "clean_wildlife"
            mock_dl.assert_called_once()


def test_universal_smart_ranking_boosts_subject_anchor(tmp_path: Path):
    """UniversalDownloader prioritizes entries containing the subject anchor and trusted channels."""
    downloader = UniversalDownloader()

    fake_entries = [
        {"id": "generic_animal", "title": "Savanna animals grazing in grass", "duration": 40.0, "height": 1080, "width": 1920},
        {"id": "honey_badger_doc", "title": "Fierce Honey Badger digging underground", "duration": 45.0, "height": 1080, "width": 1920, "uploader": "BBC Earth"},
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "honey_badger_doc.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:digging action",
                output_dir=tmp_path,
                subject_anchor="honey badger",
            )
            assert res.video_id == "honey_badger_doc"
            mock_dl.assert_called_once()


def test_sourcing_engine_injects_subject_anchor(tmp_path: Path):
    """AssetSourcingEngine prepends subject anchor to search query if missing."""
    engine = AssetSourcingEngine()
    mock_universal_info = MagicMock(
        downloaded_path=tmp_path / "mock.mp4",
        duration_sec=30.0,
        extractor="youtube",
        video_id="xyz123",
        width=1920,
        height=1080,
    )

    with patch.object(engine.universal, "download", return_value=mock_universal_info) as mock_u_dl:
        res = engine.source_scene_asset(
            scene_id="SCENE_003",
            query="nature ultimate survivor",
            preferred_vault="universal",
            subject_anchor="honey badger",
            niche_id="nature-wildlife-survival",
        )
        assert res.scene_id == "SCENE_003"
        # Check that download was called with search_target containing subject anchor
        called_args = mock_u_dl.call_args[0]
        called_search_target = called_args[0]
        assert "honey badger" in called_search_target
        assert mock_u_dl.call_args[1].get("subject_anchor") == "honey badger"


def test_universal_smart_ranking_rejects_subscribe_outro_and_zoos(tmp_path: Path):
    """UniversalDownloader rejects subscribe bumpers, sound clips, MinuteEarth stickman, and zoo enclosures."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "animoo_sound",
            "title": "What does a Hyena sound like? - Animal Sounds | Animoo Sound | Please subscribe",
            "duration": 30.0,
            "height": 1080,
            "width": 1920,
            "uploader": "Animoo Sound",
        },
        {
            "id": "minuteearth_cartoon",
            "title": "Why female hyenas are so dominant | MinuteEarth stickman",
            "duration": 90.0,
            "height": 1080,
            "width": 1920,
            "uploader": "MinuteEarth",
        },
        {
            "id": "zoo_cage",
            "title": "Hyena behind fence in zoo enclosure",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,
            "uploader": "ZooVisitor",
        },
        {
            "id": "clean_serengeti",
            "title": "Spotted hyena clan hunting wildebeest in Serengeti",
            "duration": 45.0,
            "height": 1080,
            "width": 1920,
            "uploader": "BBC Earth",
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "clean_serengeti.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:spotted hyena hunting",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                negative_terms=DEFAULT_NEGATIVE_TERMS,
            )
            assert res.video_id == "clean_serengeti"
            mock_dl.assert_called_once()


def test_universal_smart_ranking_penalizes_low_res_360p(tmp_path: Path):
    """UniversalDownloader penalizes 360p footage heavily in favor of HD/4K."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "lowres_360p",
            "title": "Spotted Hyenas: Childbirth in wildlife",
            "duration": 50.0,
            "height": 360,
            "width": 544,
        },
        {
            "id": "hd_1080p",
            "title": "Spotted Hyenas: Childbirth in wildlife",
            "duration": 50.0,
            "height": 1080,
            "width": 1920,
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "hd.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:spotted hyenas childbirth",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
            )
            assert res.video_id == "hd_1080p"


def test_universal_hard_rejection_when_all_candidates_negative(tmp_path: Path):
    """UniversalDownloader raises UniversalDownloaderError if all candidates contain prohibited negative terms."""
    from autovideo.sourcing.universal import UniversalDownloaderError

    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "cartoon_kid",
            "title": "Hyena kids cartoon song nursery baby bus",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,
        },
        {
            "id": "news_report",
            "title": "Breaking news: Hyena escape from city zoo cage",
            "duration": 45.0,
            "height": 1080,
            "width": 1920,
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with pytest.raises(UniversalDownloaderError):
            downloader.download(
                "ytsearch8:hyena kids song",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
            )


def test_coordinator_keyword_anchor_discipline():
    """Coordinator enforces anchor discipline via the REAL _build_natural_query (ADR-019).

    Previously this test re-implemented the logic inline, so it passed while production
    code diverged (root cause RC-1 in proj_f2668146).
    """
    from autovideo.coordinator import MasterPipelineCoordinator

    build = MasterPipelineCoordinator._build_natural_query
    subject_anchor = "spotted hyena"

    # Abstract keywords must be prefixed with the subject anchor
    assert build("eating dead carcass", subject_anchor) == "spotted hyena eating dead carcass"
    assert build("hệ sinh thái cân bằng", subject_anchor) == "spotted hyena hệ sinh thái cân bằng"
    # Keywords already naming the subject (full phrase or head noun) stay unchanged
    assert build("spotted hyena pack hunting", subject_anchor) == "spotted hyena pack hunting"
    assert build("hyena pack tactical hunt", subject_anchor) == "hyena pack tactical hunt"
    # Modifier-only mention does not count as the subject
    assert build("spotted deer grazing", subject_anchor) == "spotted hyena spotted deer grazing"


def test_universal_smart_ranking_rejects_tv_news_and_3d_bear_marketplace(tmp_path: Path):
    """UniversalDownloader rejects TV newscasts (HTV7), 3D asset marketplace (bear 3D model), and stock previews."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "bear_3d_model",
            "title": "Realistic Black Bear 3D Model with Fur – High-Quality Asset | VFX Ready",
            "duration": 10.0,
            "height": 1080,
            "width": 1920,
            "uploader": "PROmax3D",
        },
        {
            "id": "htv7_news",
            "title": "[HTV7] ĐỘT PHÁ MỚI TRONG TẦM SOÁT TRƯỚC SINH TẠI VIỆT NAM",
            "duration": 88.0,
            "height": 1080,
            "width": 1920,
            "uploader": "GENE SOLUTIONS",
        },
        {
            "id": "shutterstock_preview",
            "title": "Hyena running savanna footage | SHUTTERSTOCK preview watermarked",
            "duration": 25.0,
            "height": 1080,
            "width": 1920,
            "uploader": "StockClips",
        },
        {
            "id": "clean_wildlife",
            "title": "Spotted hyena clan pack hunting wildebeest",
            "duration": 45.0,
            "height": 1080,
            "width": 1920,
            "uploader": "BBC Earth",
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "clean_wildlife.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:spotted hyena hunting wildebeest",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                negative_terms=DEFAULT_NEGATIVE_TERMS,
            )
            assert res.video_id == "clean_wildlife"
            assert mock_dl.call_args[0][1] == "clean_wildlife"


def test_universal_smart_ranking_rejects_dynamic_avoid_subjects(tmp_path: Path):
    """UniversalDownloader dynamically penalizes scene-specific avoid_subjects without hardcoded lists."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "catfish_feeding",
            "title": "Catfish eating bone at the bottom of muddy pond",
            "duration": 30.0,
            "height": 1080,
            "width": 1920,
        },
        {
            "id": "villagers_crowd",
            "title": "Scared villagers walking on rural road",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,
        },
        {
            "id": "clean_hyena",
            "title": "Spotted hyena bone eating and mastication in African savanna",
            "duration": 35.0,
            "height": 1080,
            "width": 1920,
            "uploader": "BBC Earth",
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "clean_hyena.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:bone digestion acidity",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                avoid_subjects=["catfish", "villager", "crowd", "fish"],
            )
            assert res.video_id == "clean_hyena"
            assert mock_dl.call_args[0][1] == "clean_hyena"


def test_universal_smart_ranking_enforces_16_9_widescreen(tmp_path: Path):
    """UniversalDownloader penalizes 4:3 and rejects vertical video in favor of 16:9 widescreen."""
    downloader = UniversalDownloader()

    fake_entries = [
        {
            "id": "vertical_short",
            "title": "Crazy hyena sound laughing #shorts",
            "duration": 30.0,
            "height": 1920,
            "width": 1080,  # Vertical 9:16
            "uploader": "ShortsCreator",
        },
        {
            "id": "four_by_three_clip",
            "title": "Spotted hyena in Kruger National Park 2005",
            "duration": 40.0,
            "height": 720,
            "width": 960,  # 4:3 aspect ratio (960/720 = 1.33)
            "uploader": "OldSafariArchive",
        },
        {
            "id": "sixteen_by_nine_clip",
            "title": "Spotted hyenas interacting in Serengeti landscape",
            "duration": 40.0,
            "height": 1080,
            "width": 1920,  # 16:9 widescreen (1920/1080 = 1.77)
            "uploader": "SafariLive",
        },
    ]

    with patch.object(downloader, "get_video_info", return_value={"entries": fake_entries}):
        with patch.object(downloader, "_download_and_verify", return_value=tmp_path / "sixteen_by_nine_clip.mp4") as mock_dl:
            res = downloader.download(
                "ytsearch8:spotted hyenas interacting",
                output_dir=tmp_path,
                subject_anchor="spotted hyena",
                negative_terms=DEFAULT_NEGATIVE_TERMS,
            )
            assert res.video_id == "sixteen_by_nine_clip"
            assert mock_dl.call_args[0][1] == "sixteen_by_nine_clip"


