"""内置语言配置 — PowerShell。

Python port of the TypeScript ``powershellConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

powershell_config = LanguageConfig(
    id="powershell",
    displayName="PowerShell",
    extensions=[".ps1", ".psm1", ".psd1"],
    concepts=[
        "cmdlets",
        "pipelines",
        "modules",
        "functions",
        "parameters",
        "variables",
        "error handling",
    ],
    filePatterns=FilePatternConfig(),
)
