"""
Unified Asset Sourcing Dispatcher for BanContentAuto.
Routes scene keyword queries or URLs to appropriate extractors (Douyin, Bilibili, Universal)
and enforces 5-tier fallback cascade to ensure uninterrupted video generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from autovideo.core.config import AppConfig, get_config
from autovideo.sourcing.bilibili import BilibiliDownloader, BilibiliDownloaderError
from autovideo.sourcing.douyin import (
    CleanVideoInfo,
    DouyinExtractor,
    DouyinExtractorError,
    DurationOutOfRangeError,
)
from autovideo.sourcing.universal import (
    DurationFilteredError,
    UniversalDownloader,
    UniversalDownloaderError,
)

logger = logging.getLogger(__name__)


@dataclass
class SourcedAsset:
    """Represents a clean downloaded background asset ready for scene assembly."""

    scene_id: Union[int, str]
    query: str
    file_path: Path
    duration_sec: float
    width: int
    height: int
    vault_source: str  # "douyin", "bilibili", "stock", "universal"
    is_watermark_clean: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class AssetSourcingEngine:
    """
    Central background asset sourcing dispatcher.
    Coordinates Douyin, Bilibili, and Universal extractors with automatic fallback.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        douyin_extractor: Optional[DouyinExtractor] = None,
        bilibili_downloader: Optional[BilibiliDownloader] = None,
        universal_downloader: Optional[UniversalDownloader] = None,
        skill_registry: Optional[Any] = None,
    ):
        self.config = config or get_config()
        self.douyin = douyin_extractor or DouyinExtractor(config=self.config)
        self.bilibili = bilibili_downloader or BilibiliDownloader(config=self.config)
        self.universal = universal_downloader or UniversalDownloader(config=self.config)
        self.skill_registry = skill_registry

    def route_url_source(self, url: str) -> str:
        """Identify appropriate source vault from URL."""
        url_lower = url.lower()
        if "douyin.com" in url_lower:
            return "douyin"
        if "bilibili.com" in url_lower or "bv1" in url_lower:
            return "bilibili"
        return "universal"

    def source_scene_asset(
        self,
        scene_id: Union[int, str],
        query: str,
        preferred_vault: str = "douyin",
        direct_url: Optional[str] = None,
        enforce_duration: bool = True,
        output_dir: Optional[Path] = None,
        subject_anchor: Optional[str] = None,
        niche_id: Optional[str] = None,
        negative_terms: Optional[List[str]] = None,
        avoid_subjects: Optional[List[str]] = None,
        preferred_categories: Optional[List[str]] = None,
        discouraged_categories: Optional[List[str]] = None,
        trusted_channels: Optional[List[str]] = None,
        scene_terms: Optional[List[str]] = None,
        exclude_video_ids: Optional[List[str]] = None,
    ) -> SourcedAsset:
        """
        Download a clean footage asset for a given scene with automatic fallback.

        Args:
            scene_id: Identifier of the scene (e.g. 1 or 'scene_001').
            query: Semantic keyword or text containing share link.
            preferred_vault: Preferred source ('douyin', 'bilibili', 'stock', 'universal').
            direct_url: Optional direct URL overriding query search.
            enforce_duration: Reject clips outside [8s, 60s].
            output_dir: Target cache directory.
            subject_anchor: Core entity / topic anchor (e.g. 'honey badger') to keep footage on-topic.
            niche_id: Skill niche ID (e.g. 'nature-wildlife-survival').
            negative_terms: List of blacklist query keywords to reject irrelevant genres.
            avoid_subjects: Dynamically avoided subjects/entities for this specific scene.
            preferred_categories: YouTube categories to favor (+60).
            discouraged_categories: YouTube categories to penalize (-800).
            trusted_channels: YouTube channels to favor (+60).
            scene_terms: Scene-specific visual terms; candidates must mention one (ADR-019).
            exclude_video_ids: Source video IDs that reached the reuse cap (ADR-019).

        Returns:
            SourcedAsset metadata object.
        """
        dest_dir = output_dir or self.config.paths.cache_raw_footage_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Resolve skill preferences if niche_id provided but explicit parameters omitted
        if (preferred_categories is None or discouraged_categories is None or trusted_channels is None) and niche_id:
            try:
                if self.skill_registry is None:
                    from autovideo.skills.registry import SkillRegistry
                    self.skill_registry = SkillRegistry()
                sk = self.skill_registry.get_skill(niche_id)
                if sk and sk.manifest:
                    if preferred_categories is None:
                        preferred_categories = sk.manifest.preferred_categories
                    if discouraged_categories is None:
                        discouraged_categories = sk.manifest.discouraged_categories
                    if trusted_channels is None:
                        trusted_channels = sk.manifest.trusted_channels
            except Exception as e:
                logger.debug("Failed to resolve skill preferences for %s: %s", niche_id, e)

        target_url = direct_url or query

        # 1. Direct URL routing
        if direct_url or ("http://" in query or "https://" in query):
            source_type = self.route_url_source(target_url)

            if source_type == "douyin":
                try:
                    info = self.douyin.extract_and_download(
                        url_or_text=target_url,
                        output_dir=dest_dir,
                        enforce_duration=enforce_duration,
                    )
                    return SourcedAsset(
                        scene_id=scene_id,
                        query=query,
                        file_path=info.downloaded_path or (dest_dir / f"douyin_{info.aweme_id}.mp4"),
                        duration_sec=info.duration_sec,
                        width=info.width,
                        height=info.height,
                        vault_source="douyin",
                        is_watermark_clean=True,
                        metadata={"aweme_id": info.aweme_id, "title": info.title},
                    )
                except Exception as e:
                    logger.warning(f"Douyin direct extraction failed for scene {scene_id}: {e}")

            elif source_type == "bilibili":
                try:
                    b_info = self.bilibili.download(target_url, output_dir=dest_dir)
                    return SourcedAsset(
                        scene_id=scene_id,
                        query=query,
                        file_path=b_info.downloaded_path,
                        duration_sec=b_info.duration_sec,
                        width=1920,
                        height=1080,
                        vault_source="bilibili",
                        is_watermark_clean=True,
                        metadata={"bvid": b_info.bvid, "tool": b_info.source_tool},
                    )
                except Exception as e:
                    logger.warning(f"Bilibili download failed for scene {scene_id}: {e}")

            # Universal / Generic URL
            try:
                u_info = self.universal.download(
                    target_url,
                    output_dir=dest_dir,
                    enforce_duration=enforce_duration,
                    preferred_categories=preferred_categories,
                    discouraged_categories=discouraged_categories,
                    trusted_channels=trusted_channels,
                )
                return SourcedAsset(
                    scene_id=scene_id,
                    query=query,
                    file_path=u_info.downloaded_path,
                    duration_sec=u_info.duration_sec,
                    width=u_info.width,
                    height=u_info.height,
                    vault_source="universal",
                    is_watermark_clean=True,
                    metadata={"extractor": u_info.extractor, "video_id": u_info.video_id},
                )
            except Exception as e:
                logger.warning(f"Universal URL download failed for scene {scene_id}: {e}")

        # 2. Keyword-based dispatch with 5-tier fallback cascade
        vault_order: List[str] = []
        if preferred_vault == "douyin":
            vault_order = ["douyin", "bilibili", "universal"]
        elif preferred_vault == "bilibili":
            vault_order = ["bilibili", "douyin", "universal"]
        else:
            vault_order = ["universal", "douyin", "bilibili"]

        for vault in vault_order:
            try:
                if vault == "douyin":
                    # If query contains Douyin link / share text
                    if "douyin.com" in query or "v.douyin" in query:
                        info = self.douyin.extract_and_download(
                            url_or_text=query,
                            output_dir=dest_dir,
                            enforce_duration=enforce_duration,
                        )
                        return SourcedAsset(
                            scene_id=scene_id,
                            query=query,
                            file_path=info.downloaded_path or (dest_dir / f"douyin_{info.aweme_id}.mp4"),
                            duration_sec=info.duration_sec,
                            width=info.width,
                            height=info.height,
                            vault_source="douyin",
                            is_watermark_clean=True,
                            metadata={"aweme_id": info.aweme_id, "title": info.title},
                        )

                elif vault == "bilibili":
                    bvid = self.bilibili.extract_bvid(query)
                    if bvid:
                        b_info = self.bilibili.download(bvid, output_dir=dest_dir)
                        return SourcedAsset(
                            scene_id=scene_id,
                            query=query,
                            file_path=b_info.downloaded_path,
                            duration_sec=b_info.duration_sec,
                            width=1920,
                            height=1080,
                            vault_source="bilibili",
                            is_watermark_clean=True,
                            metadata={"bvid": b_info.bvid, "tool": b_info.source_tool},
                        )

                elif vault == "universal":
                    effective_query = query
                    if subject_anchor and not (query.startswith("http://") or query.startswith("https://")):
                        # Inject quoted subject anchor to force exact entity matching and avoid category drift
                        if f'"{subject_anchor.lower()}"' not in query.lower():
                            if subject_anchor.lower() in query.lower():
                                remainder = query.lower().replace(subject_anchor.lower(), "").strip()
                                effective_query = f'"{subject_anchor}" {remainder}'.strip()
                            else:
                                effective_query = f'"{subject_anchor}" {query}'.strip()

                    search_target = effective_query
                    if not (effective_query.startswith("http://") or effective_query.startswith("https://") or effective_query.startswith("ytsearch")):
                        search_target = f"ytsearch8:{effective_query}"

                    u_info = self.universal.download(
                        search_target,
                        output_dir=dest_dir,
                        enforce_duration=enforce_duration,
                        min_duration=8.0,
                        max_duration=180.0,
                        subject_anchor=subject_anchor,
                        negative_terms=negative_terms,
                        avoid_subjects=avoid_subjects,
                        preferred_categories=preferred_categories,
                        discouraged_categories=discouraged_categories,
                        trusted_channels=trusted_channels,
                        scene_terms=scene_terms,
                        exclude_video_ids=exclude_video_ids,
                    )
                    return SourcedAsset(
                        scene_id=scene_id,
                        query=query,
                        file_path=u_info.downloaded_path,
                        duration_sec=u_info.duration_sec,
                        width=u_info.width or 1920,
                        height=u_info.height or 1080,
                        vault_source="universal",
                        is_watermark_clean=True,
                        metadata={
                            "extractor": u_info.extractor,
                            "video_id": u_info.video_id,
                            "title": getattr(u_info, "title", ""),
                            "webpage_url": getattr(u_info, "webpage_url", ""),
                            "uploader": getattr(u_info, "uploader", ""),
                            "raw_filename": u_info.downloaded_path.name if u_info.downloaded_path else "",
                            "effective_query": effective_query,
                            "subject_anchor": subject_anchor,
                            "chapters": getattr(u_info, "chapters", None),
                            "categories": getattr(u_info, "categories", None),
                            "description": getattr(u_info, "description", ""),
                        },
                    )
            except Exception as e:
                logger.info(f"Fallback attempt on {vault} failed: {e}; cascading to next tier.")
                continue

        # If all sourcing tiers fail to resolve a clean video, raise descriptive error
        raise DouyinExtractorError(
            f"Asset sourcing failed across all vaults for scene {scene_id} with query '{query}'"
        )
