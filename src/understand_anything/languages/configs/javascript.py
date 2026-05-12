"""内置语言配置 — JavaScript。

Python port of the TypeScript ``javascriptConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

javascript_config = LanguageConfig(
    id="javascript",
    displayName="JavaScript",
    extensions=[".js", ".jsx", ".mjs", ".cjs"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-javascript",
        wasmFile="tree-sitter-javascript.wasm",
    ),
    concepts=[
        "closures",
        "prototypes",
        "promises",
        "async/await",
        "event loop",
        "destructuring",
        "spread operator",
        "proxies",
        "generators",
        "modules (ESM/CJS)",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["index.js", "src/index.js", "main.js"],
        barrels=["index.js"],
        tests=["*.test.js", "*.spec.js"],
        config=["package.json", "jsconfig.json"],
    ),
)
