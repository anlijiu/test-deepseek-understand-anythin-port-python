"""内置语言配置 — Swift。

Python port of the TypeScript ``swiftConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

swift_config = LanguageConfig(
    id="swift",
    displayName="Swift",
    extensions=[".swift"],
    concepts=[
        "optionals",
        "protocols",
        "extensions",
        "generics",
        "closures",
        "property wrappers",
        "result builders",
        "actors",
        "structured concurrency",
        "value types vs reference types",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["Sources/*/main.swift", "App.swift", "AppDelegate.swift"],
        barrels=[],
        tests=["*Tests.swift", "Tests/**/*.swift"],
        config=["Package.swift"],
    ),
)
