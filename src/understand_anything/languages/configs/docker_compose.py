"""内置语言配置 — Docker Compose。

Python port of the TypeScript ``dockerComposeConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

docker_compose_config = LanguageConfig(
    id="docker-compose",
    displayName="Docker Compose",
    extensions=[],
    filenames=[
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ],
    concepts=[
        "services",
        "networks",
        "volumes",
        "ports",
        "environment",
        "depends_on",
        "build context",
        "healthchecks",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["docker-compose.yml", "compose.yml"],
    ),
)
