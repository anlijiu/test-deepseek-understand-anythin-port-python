"""内置语言配置 — CSS。

Python port of the TypeScript ``cssConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

css_config = LanguageConfig(
    id="css",
    displayName="CSS",
    extensions=[".css", ".scss", ".less"],
    concepts=[
        "selectors",
        "properties",
        "media queries",
        "flexbox",
        "grid",
        "variables",
        "animations",
        "specificity",
    ],
    filePatterns=FilePatternConfig(),
)
