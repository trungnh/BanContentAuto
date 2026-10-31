"""
Publisher Module (B4: Counterpoint Thumbnail, SEO Packager, YouTube Adapter).
"""

from autovideo.publisher.image_client import (
    NineRouterImageClient,
    ThumbnailImageGenerationError,
)
from autovideo.publisher.manager import PublisherManager, PublishResult
from autovideo.publisher.seo_packager import ChapterTimestamp, SEOPackage, SEOPackager
from autovideo.publisher.thumbnail_generator import (
    CounterpointViolationError,
    SafeZoneRect,
    SafeZoneViolationError,
    THEMES,
    ThemePalette,
    ThumbnailGenerator,
    validate_counterpoint,
)
from autovideo.publisher.youtube_uploader import (
    UploadStatus,
    YouTubeUploader,
    YouTubeUploadError,
)

__all__ = [
    "ThumbnailGenerator",
    "validate_counterpoint",
    "CounterpointViolationError",
    "SafeZoneViolationError",
    "SafeZoneRect",
    "THEMES",
    "ThemePalette",
    "SEOPackage",
    "ChapterTimestamp",
    "SEOPackager",
    "YouTubeUploader",
    "UploadStatus",
    "YouTubeUploadError",
    "PublisherManager",
    "PublishResult",
    "NineRouterImageClient",
    "ThumbnailImageGenerationError",
]
