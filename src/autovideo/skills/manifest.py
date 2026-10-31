"""
Skill Manifest and Data Models for Skill Niche System (SPEC-AVF-SKILL-NICHE-V1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml
from pydantic import BaseModel, Field, field_validator


ID_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

ALLOWED_HOOKS: Set[str] = {
    "research.instructions",
    "script.plan",
    "script.rewrite",
    "scene.split",
    "prompt.image",
    "prompt.video",
    "prompt.negative",
    "prompt.thumbnail",
    "prompt.seo",
    "voice.direction",
    "subtitle.style",
    "quality.review",
}


class SkillManifest(BaseModel):
    """
    Validates skill.yaml according to SPEC-AVF-SKILL-NICHE-V1 schema.
    """
    schema_version: int = Field(1, description="Schema version, must be 1")
    id: str = Field(..., description="Unique skill ID (kebab-case)")
    name: str = Field(..., description="Full display name")
    style_name: str = Field(..., description="Aesthetic style name")
    badge: str = Field("", description="Short tag for cards / dropdown")
    version: str = Field("1.0.0", description="SemVer version")
    description: str = Field("", description="Editorial summary and positioning")
    hooks: Dict[str, str] = Field(default_factory=dict, description="Hook to relative path mapping")
    languages: List[str] = Field(default_factory=lambda: ["vi", "en"], description="Supported languages")
    permissions: List[str] = Field(default_factory=list, description="Required permissions")
    thematic_plates: List[Dict[str, Any]] = Field(default_factory=list, description="Visual references")
    preferred_categories: List[str] = Field(
        default_factory=list,
        description="YouTube categories favored for footage sourcing in this niche (e.g. Pets & Animals, Education)",
    )
    discouraged_categories: List[str] = Field(
        default_factory=list,
        description="YouTube categories penalized/avoided for footage sourcing in this niche (e.g. Howto & Style)",
    )
    fallback_search_templates: List[str] = Field(
        default_factory=list,
        description="Search query templates with {subject_anchor} for fallback sourcing (e.g. '{subject_anchor} in the wild')",
    )
    trusted_channels: List[str] = Field(
        default_factory=list,
        description="YouTube channel names favored for clean documentary B-roll in this niche",
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not ID_REGEX.match(v):
            raise ValueError(f"Invalid skill id '{v}'. Must match regex {ID_REGEX.pattern}")
        return v

    @field_validator("hooks")
    @classmethod
    def validate_hooks(cls, v: Dict[str, str]) -> Dict[str, str]:
        for hook, path_str in v.items():
            if hook not in ALLOWED_HOOKS:
                raise ValueError(f"Hook '{hook}' is not in ALLOWED_HOOKS: {sorted(ALLOWED_HOOKS)}")
            if ".." in path_str or path_str.startswith("/") or path_str.startswith("\\"):
                raise ValueError(f"Path traversal detected in hook '{hook}': {path_str}")
        return v


class Skill:
    """
    In-memory representation of an installed Skill package.
    """

    def __init__(self, directory: Path, manifest: SkillManifest, playbook_text: str = "") -> None:
        self.directory = directory.resolve()
        self.manifest = manifest
        self.playbook_text = playbook_text

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def style_name(self) -> str:
        return self.manifest.style_name

    @property
    def badge(self) -> str:
        return self.manifest.badge or self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def preferred_categories(self) -> List[str]:
        return self.manifest.preferred_categories

    @property
    def discouraged_categories(self) -> List[str]:
        return self.manifest.discouraged_categories

    @property
    def fallback_search_templates(self) -> List[str]:
        return self.manifest.fallback_search_templates

    @property
    def trusted_channels(self) -> List[str]:
        return self.manifest.trusted_channels

    def read_hook_content(self, hook_name: str) -> Optional[str]:
        """Reads relative markdown file defined for a hook."""
        rel_path = self.manifest.hooks.get(hook_name)
        if not rel_path:
            return None
        target_file = (self.directory / rel_path).resolve()
        # Security check: ensure target stays inside skill directory
        if not str(target_file).startswith(str(self.directory)):
            raise ValueError(f"Hook file traversal rejected: {rel_path}")
        if not target_file.exists():
            return None
        text = target_file.read_text(encoding="utf-8").strip()
        # Strip redundant leading hook header if present in the markdown file
        text = re.sub(r"^#+\s*Hook:\s*[a-zA-Z0-9_\-\.]+\s*\r?\n", "", text).strip()
        return text

    def content_for(self, hooks: Optional[Set[str]] = None) -> str:
        """
        Formats skill playbook and requested hooks into a cohesive prompt block.
        """
        sections: List[str] = [
            f"# Skill: {self.manifest.name} ({self.manifest.id})",
            f"Style: {self.manifest.style_name}",
            f"Badge: {self.manifest.badge}",
            f"Description: {self.manifest.description}",
        ]

        if self.playbook_text:
            sections.append(f"## Editorial Playbook (DNA)\n{self.playbook_text.strip()}")

        active_hooks = self.manifest.hooks.keys() if hooks is None else (self.manifest.hooks.keys() & hooks)
        for h in sorted(active_hooks):
            content = self.read_hook_content(h)
            if content:
                sections.append(f"## Hook: {h}\n{content.strip()}")

        return "\n\n".join(sections)
