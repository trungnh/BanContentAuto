"""
Skill Niche Subsystem (SPEC-AVF-SKILL-NICHE-V1).
Provides pluggable domain intelligence, manifests, and compilation.
"""

from autovideo.skills.manifest import ALLOWED_HOOKS, Skill, SkillManifest
from autovideo.skills.registry import SkillRegistry

__all__ = [
    "ALLOWED_HOOKS",
    "SkillManifest",
    "Skill",
    "SkillRegistry",
]
