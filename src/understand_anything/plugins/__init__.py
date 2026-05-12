"""Plugin system — analyzer plugins, language extractors, and registry."""

from __future__ import annotations

from understand_anything.plugins.extractors.types import (
    AnalyzerPlugin,
    ExtractorRegistration,
    LanguageExtractor,
    PluginModuleInfo,
)
from understand_anything.plugins.extractors.typescript import TypeScriptExtractor
from understand_anything.plugins.parsers import register_all_parsers
from understand_anything.plugins.registry import PluginRegistry
from understand_anything.plugins.tree_sitter import TreeSitterPlugin

__all__ = [
    "AnalyzerPlugin",
    "ExtractorRegistration",
    "LanguageExtractor",
    "PluginModuleInfo",
    "PluginRegistry",
    "TreeSitterPlugin",
    "TypeScriptExtractor",
    "register_all_parsers",
]
