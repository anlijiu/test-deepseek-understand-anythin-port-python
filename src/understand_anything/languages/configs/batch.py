"""内置语言配置 — Batch Script。

Python port of the TypeScript ``batchConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

batch_config = LanguageConfig(
    id="batch",
    displayName="Batch Script",
    extensions=[".bat", ".cmd"],
    concepts=[
        "commands",
        "variables",
        "labels",
        "goto",
        "call",
        "echo",
        "set",
        "for loops",
        "if conditions",
    ],
    filePatterns=FilePatternConfig(),
)
