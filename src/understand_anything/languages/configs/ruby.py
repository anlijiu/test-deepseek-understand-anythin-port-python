"""内置语言配置 — Ruby。

Python port of the TypeScript ``rubyConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import (
    FilePatternConfig,
    LanguageConfig,
    TreeSitterConfig,
)

ruby_config = LanguageConfig(
    id="ruby",
    displayName="Ruby",
    extensions=[".rb", ".rake"],
    treeSitter=TreeSitterConfig(
        wasmPackage="tree-sitter-ruby",
        wasmFile="tree-sitter-ruby.wasm",
    ),
    concepts=[
        "blocks and procs",
        "mixins",
        "metaprogramming",
        "duck typing",
        "DSLs",
        "monkey patching",
        "symbols",
        "method_missing",
        "open classes",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["config.ru", "app.rb"],
        barrels=[],
        tests=["*_test.rb", "*_spec.rb", "spec_helper.rb"],
        config=["Gemfile", "Rakefile"],
    ),
)
