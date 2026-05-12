"""内置语言配置 — C++。

Python port of the TypeScript ``cppConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

cpp_config = LanguageConfig(
    id="cpp",
    displayName="C++",
    extensions=[".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-cpp",
        wasmFile="tree-sitter-cpp.wasm",
    ),
    concepts=[
        "templates",
        "RAII",
        "smart pointers",
        "move semantics",
        "operator overloading",
        "virtual functions",
        "namespaces",
        "constexpr",
        "lambda expressions",
        "STL containers",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["main.cpp", "src/main.cpp"],
        barrels=[],
        tests=["*_test.cpp", "*_test.cc", "test_*.cpp"],
        config=["CMakeLists.txt", "Makefile", "meson.build"],
    ),
)
