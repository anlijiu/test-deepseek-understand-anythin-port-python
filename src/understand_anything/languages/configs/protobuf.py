"""内置语言配置 — Protocol Buffers。

Python port of the TypeScript ``protobufConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

protobuf_config = LanguageConfig(
    id="protobuf",
    displayName="Protocol Buffers",
    extensions=[".proto"],
    concepts=[
        "messages",
        "services",
        "enums",
        "oneof",
        "repeated fields",
        "maps",
        "packages",
        "imports",
    ],
    filePatterns=FilePatternConfig(),
)
