"""内置语言配置 — Go。

Python port of the TypeScript ``goConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

go_config = LanguageConfig(
    id="go",
    displayName="Go",
    extensions=[".go"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-go",
        wasmFile="tree-sitter-go.wasm",
    ),
    concepts=[
        "goroutines",
        "channels",
        "interfaces",
        "struct embedding",
        "error handling patterns",
        "defer/panic/recover",
        "slices",
        "pointers",
        "concurrency patterns",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["main.go", "cmd/*/main.go"],
        barrels=[],
        tests=["*_test.go"],
        config=["go.mod", "go.sum"],
    ),
)
