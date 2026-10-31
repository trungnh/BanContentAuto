"""
Asset Sourcing Engine for BanContentAuto.
Provides Douyin (pure Python A_Bogus), Bilibili (BBDown wrapper), and Universal (yt-dlp) extractors.
"""

from autovideo.sourcing.a_bogus import ABogusSigner
from autovideo.sourcing.bilibili import (
    BilibiliDownloader,
    BilibiliDownloaderError,
    BilibiliVideoInfo,
)
from autovideo.sourcing.douyin import (
    CleanVideoInfo,
    DouyinExtractor,
    DouyinExtractorError,
    DurationOutOfRangeError,
    RateLimitError,
    VideoNotFoundError,
)
from autovideo.sourcing.engine import AssetSourcingEngine, SourcedAsset
from autovideo.sourcing.universal import (
    DurationFilteredError,
    UniversalDownloader,
    UniversalDownloaderError,
    UniversalVideoInfo,
)

__all__ = [
    "ABogusSigner",
    "DouyinExtractor",
    "CleanVideoInfo",
    "DouyinExtractorError",
    "VideoNotFoundError",
    "DurationOutOfRangeError",
    "RateLimitError",
    "BilibiliDownloader",
    "BilibiliDownloaderError",
    "BilibiliVideoInfo",
    "UniversalDownloader",
    "UniversalDownloaderError",
    "DurationFilteredError",
    "UniversalVideoInfo",
    "AssetSourcingEngine",
    "SourcedAsset",
]
