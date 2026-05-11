"""Plugin system — analyzer plugins and language extractors."""

from __future__ import annotations

from understand_anything.plugins.extractors.types import (
    AnalyzerPlugin,
    ExtractorRegistration,
    LanguageExtractor,
    PluginModuleInfo,
)
from understand_anything.plugins.extractors.typescript import TypeScriptExtractor
from understand_anything.plugins.tree_sitter import TreeSitterPlugin

__all__ = [
    "AnalyzerPlugin",
    "ExtractorRegistration",
    "LanguageExtractor",
    "PluginModuleInfo",
    "TreeSitterPlugin",
    "TypeScriptExtractor",
]
