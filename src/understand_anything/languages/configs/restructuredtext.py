"""内置语言配置 — reStructuredText。

Python port of the TypeScript ``restructuredtextConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

restructuredtext_config = LanguageConfig(
    id="restructuredtext",
    displayName="reStructuredText",
    extensions=[".rst"],
    concepts=[
        "headings",
        "directives",
        "roles",
        "cross-references",
        "toctree",
        "code blocks",
        "admonitions",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["index.rst"],
    ),
)
