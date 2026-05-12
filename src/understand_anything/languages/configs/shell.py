"""内置语言配置 — Shell Script。

Python port of the TypeScript ``shellConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

shell_config = LanguageConfig(
    id="shell",
    displayName="Shell Script",
    extensions=[".sh", ".bash", ".zsh"],
    concepts=[
        "variables",
        "functions",
        "conditionals",
        "loops",
        "pipes",
        "redirection",
        "subshells",
        "exit codes",
    ],
    filePatterns=FilePatternConfig(
        config=[".bashrc", ".zshrc", ".profile"],
    ),
)
