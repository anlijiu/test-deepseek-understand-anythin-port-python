"""内置语言配置 — Jenkinsfile。

Python port of the TypeScript ``jenkinsfileConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

jenkinsfile_config = LanguageConfig(
    id="jenkinsfile",
    displayName="Jenkinsfile",
    extensions=[],
    filenames=["Jenkinsfile"],
    concepts=[
        "pipeline",
        "stages",
        "steps",
        "agents",
        "environment",
        "post actions",
        "parallel execution",
        "shared libraries",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["Jenkinsfile"],
    ),
)
