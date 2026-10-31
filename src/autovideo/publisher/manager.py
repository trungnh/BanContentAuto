"""
Publisher Manager (B4 Orchestrator, REQ-B4-01, REQ-B4-02, VAC-UI-04).
Coordinates the complete B4 Stage:
1. Counterpoint Thumbnail generation with YouTube safe-zone enforcement.
2. Diagnostic safe-zone overlay generation for UI review.
3. Full YouTube SEO Package generation and export to renders/{project_id}/seo.md.
4. Optional 1-Click direct upload via YouTubeUploader.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from autovideo.core.config import AppConfig, get_config
from autovideo.publisher.seo_packager import SEOPackage, SEOPackager
from autovideo.publisher.thumbnail_generator import ThumbnailGenerator
from autovideo.publisher.youtube_uploader import UploadStatus, YouTubeUploader

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Consolidated results of the B4 packaging process."""
    project_id: str
    output_dir: Path
    thumbnail_path: Path
    thumbnail_preview_path: Path
    seo_markdown_path: Path
    seo_package: SEOPackage
    video_path: Optional[Path] = None
    upload_status: Optional[UploadStatus] = None


class PublisherManager:
    """
    Central coordinator for Step 4 (B4) Publishing & Packaging.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        mock_uploader: bool = True,
        credentials_path: Optional[Union[Path, str]] = None,
    ) -> None:
        self.config = config or get_config()
        pub_cfg = getattr(self.config, "publishing", None)

        thumb_w = pub_cfg.thumbnail_width if pub_cfg else 1920
        thumb_h = pub_cfg.thumbnail_height if pub_cfg else 1080
        safe_w = pub_cfg.safe_zone_width_ratio if pub_cfg else 0.20
        safe_h = pub_cfg.safe_zone_height_ratio if pub_cfg else 0.25
        default_theme = pub_cfg.default_theme if pub_cfg else "dark_dramatic"

        self.thumbnail_generator = ThumbnailGenerator(
            width=thumb_w,
            height=thumb_h,
            safe_zone_width_ratio=safe_w,
            safe_zone_height_ratio=safe_h,
            default_theme=default_theme,
        )
        self.seo_packager = SEOPackager()
        self.uploader = YouTubeUploader(
            credentials_path=credentials_path,
            mock_mode=mock_uploader,
        )

    def prepare_publishing_package(
        self,
        project_id: str,
        topic: str,
        chapters: Sequence[Any],
        thumbnail_hook: Optional[str] = None,
        thumbnail_badge: Optional[str] = None,
        base_image: Optional[Union[Path, str]] = None,
        video_path: Optional[Union[Path, str]] = None,
        theme: Optional[str] = None,
        category_id: Optional[str] = None,
        strict_counterpoint: bool = True,
        seo_input: Optional[Any] = None,
        skill: Optional[Any] = None,
    ) -> PublishResult:
        """
        Executes the packaging workflow: generates thumbnail, diagnostic preview,
        and saves seo.md using dynamic LLM-generated SEO & active skill niche rules.
        """
        # Determine output directory
        project_dir = self.config.paths.get_project_render_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        thumb_path = project_dir / "thumbnail.jpg"
        preview_path = project_dir / "thumbnail_safe_zone_preview.jpg"
        seo_path = project_dir / "seo.md"

        # 1. Generate SEO Package first to obtain Title options and metadata
        seo_pkg = self.seo_packager.generate_package(
            project_id=project_id,
            topic=topic,
            chapters=chapters,
            category_id=category_id,
            seo_input=seo_input,
            skill=skill,
        )

        final_hook = thumbnail_hook or seo_pkg.thumbnail_hook or topic[:25]
        final_badge = thumbnail_badge or seo_pkg.thumbnail_badge or (getattr(skill, "badge", None) if skill else "TIÊU ĐIỂM")

        # 1.5 Generate AI raw base image via 9Router Text-to-Image if not supplied
        raw_thumb_path = project_dir / "thumbnail_raw.jpg"
        if not base_image:
            prompt_to_use = getattr(seo_pkg, "thumbnail_prompt", None) or (
                f"Dramatic photorealistic documentary thumbnail of {topic}, cinematic 8k lighting, empty bottom-right safe zone"
            )
            try:
                from autovideo.core.settings import SettingsManager
                from autovideo.publisher.image_client import NineRouterImageClient
                sm = SettingsManager(config=self.config)
                stg = sm.get_settings()
                if getattr(stg, "image_provider", "9router") != "none":
                    logger.info("Generating AI thumbnail base image via 9Router with model '%s'...", getattr(stg, "image_model", "ag/gemini-3.8-flash"))
                    img_client = NineRouterImageClient()
                    img_client.generate_image(
                        prompt=prompt_to_use,
                        output_path=raw_thumb_path,
                        model=getattr(stg, "image_model", None),
                    )
                    if raw_thumb_path.exists() and raw_thumb_path.stat().st_size > 0:
                        base_image = raw_thumb_path
            except Exception as img_err:
                logger.error("Failed to generate AI thumbnail image via 9Router: %s", img_err)
                raise

        # 2. Generate Counterpoint Thumbnail, validating against primary title
        primary_title = seo_pkg.get_primary_title()
        self.thumbnail_generator.generate(
            hook_text=final_hook,
            tension_badge=final_badge,
            base_image=base_image,
            output_path=thumb_path,
            theme_name=theme,
            title_to_check=primary_title,
            strict_counterpoint=strict_counterpoint,
        )

        # 3. Generate Diagnostic Safe-Zone Preview Overlay (for VAC-UI-04)
        self.thumbnail_generator.render_safe_zone_overlay(
            image_or_path=thumb_path,
            output_path=preview_path,
        )

        # 4. Export seo.md
        self.seo_packager.export_markdown(seo_pkg, output_path=seo_path)

        resolved_video_path = Path(video_path).resolve() if video_path else None

        return PublishResult(
            project_id=project_id,
            output_dir=project_dir,
            thumbnail_path=thumb_path,
            thumbnail_preview_path=preview_path,
            seo_markdown_path=seo_path,
            seo_package=seo_pkg,
            video_path=resolved_video_path,
            upload_status=None,
        )

    def publish_to_youtube(
        self,
        publish_result: PublishResult,
        privacy_status: str = "private",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> UploadStatus:
        """
        Publishes the completed package to YouTube (1-Click Publish REQ-B4-02).
        """
        if not publish_result.video_path or not publish_result.video_path.exists():
            raise FileNotFoundError(f"Video file not found or not rendered: {publish_result.video_path}")

        primary_title = publish_result.seo_package.get_primary_title()
        status = self.uploader.upload_video(
            video_path=publish_result.video_path,
            title=primary_title,
            description=publish_result.seo_package.description,
            tags=publish_result.seo_package.tags,
            category_id=publish_result.seo_package.category_id,
            privacy_status=privacy_status,
            thumbnail_path=publish_result.thumbnail_path,
            progress_callback=progress_callback,
        )

        publish_result.upload_status = status
        return status
