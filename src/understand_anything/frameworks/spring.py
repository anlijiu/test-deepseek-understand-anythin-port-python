"""内置框架配置 — Spring Boot。

Python port of the TypeScript ``springConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FrameworkConfig

spring_config = FrameworkConfig(
    id="spring",
    displayName="Spring Boot",
    languages=["java", "kotlin"],
    detectionKeywords=[
        "spring-boot",
        "spring-boot-starter",
        "spring-web",
        "spring-data",
        "org.springframework",
    ],
    manifestFiles=["pom.xml", "build.gradle", "build.gradle.kts"],
    promptSnippetPath="./frameworks/spring.md",
    entryPoints=["**/Application.java", "**/App.java"],
    layerHints={
        "controller": "api",
        "service": "service",
        "repository": "data",
        "model": "data",
        "entity": "data",
        "config": "config",
        "dto": "types",
        "security": "middleware",
    },
)
