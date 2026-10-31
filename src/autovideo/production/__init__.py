"""
Production and scene assembly module for BanContentAuto.
Handles 16:9 blurred transformation, atomic scene muxing,
rolling disk buffer management, modular chapter building, and fast concat demuxing.
"""

from autovideo.production.chapter_builder import (
    ChapterBuilder,
    ChapterBuilderError,
    ChapterRenderResult,
    PipelineCheckpoint,
    ProductionPipeline,
    ProductionResult,
    SceneAssets,
)
from autovideo.production.concat_demuxer import (
    ConcatDemuxer,
    ConcatDemuxerError,
    ConcatResult,
)
from autovideo.production.rolling_buffer import RollingDiskBuffer
from autovideo.production.scene_muxer import SceneMuxConfig, SceneMuxResult, SceneMuxer
from autovideo.production.transformer import (
    HighlightConfig,
    TransformationConfig,
    VideoProbeInfo,
    VideoTransformer,
    detect_crop_region,
    probe_video,
)

__all__ = [
    "ChapterBuilder",
    "ChapterBuilderError",
    "ChapterRenderResult",
    "ConcatDemuxer",
    "ConcatDemuxerError",
    "ConcatResult",
    "HighlightConfig",
    "PipelineCheckpoint",
    "ProductionPipeline",
    "ProductionResult",
    "RollingDiskBuffer",
    "SceneAssets",
    "SceneMuxConfig",
    "SceneMuxResult",
    "SceneMuxer",
    "TransformationConfig",
    "VideoProbeInfo",
    "VideoTransformer",
    "detect_crop_region",
    "probe_video",
]
