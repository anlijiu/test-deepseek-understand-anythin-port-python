"""内置语言配置 — JSON。

Python port of the TypeScript ``jsonConfigConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

json_config = LanguageConfig(
    id="json",
    displayName="JSON",
    extensions=[".json", ".jsonc"],
    concepts=[
        "objects",
        "arrays",
        "nesting",
        "schema references",
        "comments (JSONC)",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["package.json"],
        config=["tsconfig.json", "package.json", ".eslintrc.json"],
    ),
)
