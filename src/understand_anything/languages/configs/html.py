"""内置语言配置 — HTML。

Python port of the TypeScript ``htmlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

html_config = LanguageConfig(
    id="html",
    displayName="HTML",
    extensions=[".html", ".htm"],
    concepts=[
        "elements",
        "attributes",
        "semantic tags",
        "forms",
        "meta tags",
        "scripts",
        "stylesheets",
        "accessibility",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["index.html"],
    ),
)
