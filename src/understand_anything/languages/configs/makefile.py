"""内置语言配置 — Makefile。

Python port of the TypeScript ``makefileConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

makefile_config = LanguageConfig(
    id="makefile",
    displayName="Makefile",
    extensions=[".mk"],
    filenames=["Makefile", "GNUmakefile", "makefile"],
    concepts=[
        "targets",
        "dependencies",
        "recipes",
        "variables",
        "pattern rules",
        "phony targets",
        "includes",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["Makefile"],
    ),
)
