"""内置语言配置 — OpenAPI。

Python port of the TypeScript ``openapiConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

openapi_config = LanguageConfig(
    id="openapi",
    displayName="OpenAPI",
    extensions=[],
    filenames=[
        "openapi.yaml",
        "openapi.json",
        "swagger.yaml",
        "swagger.json",
    ],
    concepts=[
        "paths",
        "operations",
        "schemas",
        "parameters",
        "responses",
        "security schemes",
        "tags",
        "servers",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["openapi.yaml", "swagger.yaml"],
    ),
)
