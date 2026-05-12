"""内置语言配置 — TOML。

Python port of the TypeScript ``tomlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

toml_config = LanguageConfig(
    id="toml",
    displayName="TOML",
    extensions=[".toml"],
    concepts=[
        "tables",
        "inline tables",
        "arrays of tables",
        "key-value pairs",
        "dotted keys",
    ],
    filePatterns=FilePatternConfig(
        config=["Cargo.toml", "pyproject.toml", "netlify.toml"],
    ),
)
