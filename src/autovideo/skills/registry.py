"""
Skill Registry Service for Scanning, Compiling, and Managing Skill Niches (SPEC-AVF-SKILL-NICHE-V1).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set
import yaml

from autovideo.skills.manifest import ALLOWED_HOOKS, Skill, SkillManifest

logger = logging.getLogger(__name__)


HOOK_EXTRACT_REGEX = re.compile(
    r"(?:^|\r?\n)##\s*Hook:\s*{hook_name}\s*\r?\n(.*?)(?=(?:\r?\n##\s*Hook:|\r?\n+(?:---\s*\r?\n+)?#\s*Skill:|\Z))",
    re.DOTALL,
)


class SkillRegistry:
    """
    Manages loading, validation, compilation, and hook extraction for Skill Niches.
    """

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        if root_dir is None:
            # Default to 'skills' directory in project root
            # Assuming this file is at src/autovideo/skills/registry.py -> 3 levels up to project root
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.root_dir = project_root / "skills"
        else:
            self.root_dir = Path(root_dir).resolve()

        self._cache: Dict[str, Skill] = {}

    def reload(self) -> None:
        """Clears memory cache to force re-scanning skills from disk."""
        self._cache.clear()

    def list_skills(self) -> List[Skill]:
        """
        Scans root_dir for all subdirectories containing a valid skill.yaml.
        Returns a list of Skill objects sorted by name.
        """
        skills: List[Skill] = []
        if not self.root_dir.exists():
            return skills

        for entry in self.root_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "skill.yaml"
            if manifest_path.exists():
                try:
                    skill = self._load_skill_from_dir(entry)
                    skills.append(skill)
                    self._cache[skill.id] = skill
                except Exception as exc:
                    logger.warning("Failed to load skill from %s: %s", entry, exc)

        return sorted(skills, key=lambda s: s.name)

    def get_skill(self, skill_id: str) -> Skill:
        """
        Retrieves a skill by its unique ID.
        Raises KeyError if not found.
        """
        if skill_id in self._cache:
            return self._cache[skill_id]

        # Scan folder directly
        candidate_dir = self.root_dir / skill_id
        if candidate_dir.is_dir() and (candidate_dir / "skill.yaml").exists():
            skill = self._load_skill_from_dir(candidate_dir)
            self._cache[skill.id] = skill
            return skill

        # Fallback scan all
        for s in self.list_skills():
            if s.id == skill_id:
                return s

        raise KeyError(f"Skill '{skill_id}' not found in registry at {self.root_dir}")

    def _load_skill_from_dir(self, skill_dir: Path) -> Skill:
        manifest_path = skill_dir / "skill.yaml"
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        manifest = SkillManifest(**raw_data)

        playbook_path = skill_dir / "SKILL.md"
        playbook_text = ""
        if playbook_path.exists():
            playbook_text = playbook_path.read_text(encoding="utf-8")

        return Skill(directory=skill_dir, manifest=manifest, playbook_text=playbook_text)

    def compile(self, skill_ids: Sequence[str], hooks: Optional[Set[str]] = None) -> str:
        """
        Compiles one or more skills into a single cohesive creative guidance block.
        Ensures skills are not duplicated.
        """
        if not skill_ids:
            return ""

        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("A skill may only be selected once in compilation")

        compiled_blocks: List[str] = []
        for sid in skill_ids:
            skill = self.get_skill(sid)
            compiled_blocks.append(skill.content_for(hooks=hooks))

        return "\n\n---\n\n".join(compiled_blocks)

    @staticmethod
    def extract_hook_content(content: str, hook_name: str) -> str:
        """
        Extracts only the content block for a specific hook from compiled guidance.
        """
        pattern = re.compile(
            rf"(?:^|\r?\n)##\s*Hook:\s*{re.escape(hook_name)}\s*\r?\n(.*?)(?=(?:\r?\n##\s*Hook:|\r?\n+(?:---\s*\r?\n+)?#\s*Skill:|\Z))",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        return ""
