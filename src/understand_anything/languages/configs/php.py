"""内置语言配置 — PHP。

Python port of the TypeScript ``phpConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

php_config = LanguageConfig(
    id="php",
    displayName="PHP",
    extensions=[".php"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-php",
        wasmFile="tree-sitter-php.wasm",
    ),
    concepts=[
        "namespaces",
        "traits",
        "type declarations",
        "attributes",
        "enums",
        "fibers",
        "closures",
        "magic methods",
        "dependency injection",
        "middleware",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["index.php", "public/index.php", "artisan"],
        barrels=[],
        tests=["*Test.php", "tests/**/*.php"],
        config=["composer.json", "php.ini"],
    ),
)
