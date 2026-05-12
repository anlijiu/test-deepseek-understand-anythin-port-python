"""内置语言配置 — Plain Text。

Python port of the TypeScript ``plaintextConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

plaintext_config = LanguageConfig(
    id="plaintext",
    displayName="Plain Text",
    extensions=[".txt", ".text"],
    concepts=["paragraphs", "lists", "sections"],
    filePatterns=FilePatternConfig(),
)
