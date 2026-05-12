"""内置语言配置 — C#。

Python port of the TypeScript ``csharpConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

csharp_config = LanguageConfig(
    id="csharp",
    displayName="C#",
    extensions=[".cs"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-c-sharp",
        wasmFile="tree-sitter-c_sharp.wasm",
    ),
    concepts=[
        "LINQ",
        "async/await",
        "generics",
        "properties",
        "delegates and events",
        "attributes",
        "nullable reference types",
        "pattern matching",
        "records",
        "dependency injection",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["Program.cs", "**/Program.cs"],
        barrels=[],
        tests=["*Tests.cs", "*Test.cs"],
        config=["*.csproj", "*.sln"],
    ),
)
