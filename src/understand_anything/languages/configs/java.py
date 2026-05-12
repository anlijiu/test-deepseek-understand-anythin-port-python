"""内置语言配置 — Java。

Python port of the TypeScript ``javaConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

java_config = LanguageConfig(
    id="java",
    displayName="Java",
    extensions=[".java"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-java",
        wasmFile="tree-sitter-java.wasm",
    ),
    concepts=[
        "generics",
        "annotations",
        "interfaces",
        "abstract classes",
        "streams API",
        "lambdas",
        "sealed classes",
        "records",
        "dependency injection",
        "checked exceptions",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=[
            "**/Application.java",
            "**/Main.java",
            "src/main/java/**/App.java",
        ],
        barrels=[],
        tests=["*Test.java", "*Tests.java", "*IT.java"],
        config=["pom.xml", "build.gradle", "build.gradle.kts"],
    ),
)
