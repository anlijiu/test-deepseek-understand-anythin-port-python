"""内置语言配置 — Dockerfile。

Python port of the TypeScript ``dockerfileConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

dockerfile_config = LanguageConfig(
    id="dockerfile",
    displayName="Dockerfile",
    extensions=[],
    filenames=[
        "Dockerfile",
        "Dockerfile.dev",
        "Dockerfile.prod",
        "Dockerfile.test",
    ],
    concepts=[
        "multi-stage builds",
        "layers",
        "base images",
        "COPY/ADD",
        "EXPOSE",
        "ENTRYPOINT",
        "CMD",
        "ARG",
        "ENV",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["Dockerfile"],
    ),
)
