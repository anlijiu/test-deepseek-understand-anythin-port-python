"""语言和框架系统 — 配置、注册表和检测。

提供语言配置、框架检测和插件发现的核心基础设施。
"""
from __future__ import annotations

from understand_anything.languages.framework_registry import FrameworkRegistry
from understand_anything.languages.registry import LanguageRegistry
from understand_anything.languages.types import (
    FilePatternConfig,
    FrameworkConfig,
    LanguageConfig,
    StrictLanguageConfig,
    TreeSitterConfig,
)

__all__ = [
    "FilePatternConfig",
    "FrameworkConfig",
    "FrameworkRegistry",
    "LanguageConfig",
    "LanguageRegistry",
    "StrictLanguageConfig",
    "TreeSitterConfig",
]
