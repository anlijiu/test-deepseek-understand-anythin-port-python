"""内置语言配置 — JSON Schema。

Python port of the TypeScript ``jsonSchemaConfig``.

TODO: JSON Schema 文件没有唯一扩展名 — *.schema.json 文件会通过 .json 扩展名
匹配到 ``json_config``。需要基于内容的检测（检查 ``"$schema"`` 键）。
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

json_schema_config = LanguageConfig(
    id="json-schema",
    displayName="JSON Schema",
    extensions=[],
    concepts=[
        "types",
        "properties",
        "required fields",
        "$ref",
        "$defs",
        "allOf/anyOf/oneOf",
        "patterns",
        "validation",
    ],
    filePatterns=FilePatternConfig(),
)
