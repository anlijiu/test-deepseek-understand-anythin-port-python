"""内置语言配置 — CSV。

Python port of the TypeScript ``csvConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

csv_config = LanguageConfig(
    id="csv",
    displayName="CSV",
    extensions=[".csv", ".tsv"],
    concepts=["headers", "rows", "delimiters", "quoting", "escaping"],
    filePatterns=FilePatternConfig(),
)
