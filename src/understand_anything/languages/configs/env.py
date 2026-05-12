"""内置语言配置 — Environment Variables。

Python port of the TypeScript ``envConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

env_config = LanguageConfig(
    id="env",
    displayName="Environment Variables",
    extensions=[".env"],
    filenames=[
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        ".env.example",
    ],
    concepts=[
        "key-value pairs",
        "variable interpolation",
        "secrets",
        "environment-specific config",
    ],
    filePatterns=FilePatternConfig(
        config=[".env", ".env.*"],
    ),
)
