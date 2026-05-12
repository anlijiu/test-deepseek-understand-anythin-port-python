"""内置语言配置 — YAML。

Python port of the TypeScript ``yamlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

yaml_config = LanguageConfig(
    id="yaml",
    displayName="YAML",
    extensions=[".yaml", ".yml"],
    concepts=[
        "mappings",
        "sequences",
        "anchors",
        "aliases",
        "multi-document",
        "tags",
    ],
    filePatterns=FilePatternConfig(
        config=["*.yaml", "*.yml"],
    ),
)
