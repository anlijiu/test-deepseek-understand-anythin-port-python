"""内置语言配置 — Lua。

Python port of the TypeScript ``luaConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

lua_config = LanguageConfig(
    id="lua",
    displayName="Lua",
    extensions=[".lua"],
    concepts=[
        "tables",
        "metatables",
        "coroutines",
        "closures",
        "prototype-based OOP",
        "varargs",
        "weak references",
        "environments",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["main.lua", "init.lua"],
        barrels=[],
        tests=["*_test.lua", "test_*.lua", "*_spec.lua"],
        config=[".luacheckrc", "rockspec"],
    ),
)
