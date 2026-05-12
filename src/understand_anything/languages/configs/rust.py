"""内置语言配置 — Rust。

Python port of the TypeScript ``rustConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

rust_config = LanguageConfig(
    id="rust",
    displayName="Rust",
    extensions=[".rs"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-rust",
        wasmFile="tree-sitter-rust.wasm",
    ),
    concepts=[
        "ownership",
        "borrowing",
        "lifetimes",
        "traits",
        "pattern matching",
        "enums with data",
        "error handling (Result/Option)",
        "macros",
        "async/await",
        "unsafe blocks",
        "generics",
        "closures",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["src/main.rs", "src/lib.rs"],
        barrels=["mod.rs", "lib.rs"],
        tests=["tests/*.rs"],
        config=["Cargo.toml"],
    ),
)
