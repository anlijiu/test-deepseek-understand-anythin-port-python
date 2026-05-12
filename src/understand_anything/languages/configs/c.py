"""内置语言配置 — C。

Python port of the TypeScript ``cConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

c_config = LanguageConfig(
    id="c",
    displayName="C",
    extensions=[".c", ".h"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-cpp",
        wasmFile="tree-sitter-cpp.wasm",
    ),
    concepts=[
        "pointers",
        "manual memory management",
        "structs",
        "unions",
        "function pointers",
        "preprocessor macros",
        "header files",
        "static vs dynamic linking",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["main.c", "src/main.c"],
        barrels=[],
        tests=["*_test.c", "test_*.c"],
        config=["Makefile", "CMakeLists.txt", "meson.build"],
    ),
)
