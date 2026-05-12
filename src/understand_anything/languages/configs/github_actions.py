"""内置语言配置 — GitHub Actions。

Python port of the TypeScript ``githubActionsConfig``.

TODO: GitHub Actions 清单文件是 YAML，没有唯一扩展名或文件名。
当前无法通过注册表检测（无扩展名、无文件名），需要基于内容的检测。
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

github_actions_config = LanguageConfig(
    id="github-actions",
    displayName="GitHub Actions",
    extensions=[],
    concepts=[
        "workflows",
        "jobs",
        "steps",
        "actions",
        "triggers",
        "secrets",
        "matrix strategy",
        "artifacts",
    ],
    filePatterns=FilePatternConfig(
        config=[".github/workflows/*.yml"],
    ),
)
