"""内置语言配置 — Markdown。

Python port of the TypeScript ``markdownConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

markdown_config = LanguageConfig(
    id="markdown",
    displayName="Markdown",
    extensions=[".md", ".mdx"],
    concepts=[
        "headings",
        "links",
        "code blocks",
        "front matter",
        "lists",
        "tables",
        "images",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["README.md"],
    ),
)
