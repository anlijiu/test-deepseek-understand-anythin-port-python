"""内置语言配置 — Kotlin。

Python port of the TypeScript ``kotlinConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

kotlin_config = LanguageConfig(
    id="kotlin",
    displayName="Kotlin",
    extensions=[".kt", ".kts"],
    concepts=[
        "coroutines",
        "data classes",
        "sealed classes",
        "extension functions",
        "null safety",
        "delegation",
        "DSL builders",
        "inline functions",
        "companion objects",
        "flow",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["**/Application.kt", "**/Main.kt"],
        barrels=[],
        tests=["*Test.kt", "*Tests.kt"],
        config=["build.gradle.kts", "build.gradle"],
    ),
)
