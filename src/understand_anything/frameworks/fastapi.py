"""内置框架配置 — FastAPI。

Python port of the TypeScript ``fastapiConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FrameworkConfig

fastapi_config = FrameworkConfig(
    id="fastapi",
    displayName="FastAPI",
    languages=["python"],
    detectionKeywords=["fastapi", "uvicorn", "starlette"],
    manifestFiles=[
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
    ],
    promptSnippetPath="./frameworks/fastapi.md",
    entryPoints=["main.py", "app.py"],
    layerHints={
        "routers": "api",
        "schemas": "types",
        "models": "data",
        "dependencies": "service",
        "crud": "service",
        "api": "api",
    },
)
