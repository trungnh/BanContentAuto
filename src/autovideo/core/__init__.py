"""
Core foundation components: configuration and external binary management.
"""

from autovideo.core.config import (
    AppConfig,
    ComplianceConfig,
    PathConfig,
    PerformanceConfig,
    ScriptBudgetConfig,
    SourcingConfig,
    get_config,
)
from autovideo.core.binary_manager import (
    BinaryInfo,
    BinaryManager,
    BinaryNotFoundError,
)

__all__ = [
    "AppConfig",
    "PathConfig",
    "PerformanceConfig",
    "ComplianceConfig",
    "SourcingConfig",
    "ScriptBudgetConfig",
    "get_config",
    "BinaryInfo",
    "BinaryManager",
    "BinaryNotFoundError",
]
