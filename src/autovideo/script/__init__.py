"""
Scriptwriting and Screenplay Generation Brain for BanContentAuto (Stage 1 / Bước 1).
Includes Anti-AI Linter, Word Budget Engine, Persona Prompts, and Multi-Agent Pipeline.
"""

from autovideo.script.anti_ai_linter import AntiAILinter, LintResult, BANNED_PATTERNS_35
from autovideo.script.word_budget import WordBudgetValidator, calculate_scene_budget, estimate_duration
from autovideo.script.prompts import PersonaRegistry, PromptCompiler, COLD_OPEN_RULES, COUNTERPOINT_RULES
from autovideo.script.pipeline import (
    ScriptwritingPipeline,
    BaseLLMAdapter,
    GeminiFlashAdapter,
    NineRouterAdapter,
    Screenplay,
    Chapter,
    Scene,
    SceneKeyword,
    SEOPackage,
)

__all__ = [
    "AntiAILinter",
    "LintResult",
    "BANNED_PATTERNS_35",
    "WordBudgetValidator",
    "calculate_scene_budget",
    "estimate_duration",
    "PersonaRegistry",
    "PromptCompiler",
    "COLD_OPEN_RULES",
    "COUNTERPOINT_RULES",
    "ScriptwritingPipeline",
    "BaseLLMAdapter",
    "GeminiFlashAdapter",
    "NineRouterAdapter",
    "Screenplay",
    "Chapter",
    "Scene",
    "SceneKeyword",
    "SEOPackage",
]
