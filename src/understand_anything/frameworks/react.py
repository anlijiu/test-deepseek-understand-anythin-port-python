"""内置框架配置 — React。

Python port of the TypeScript ``reactConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FrameworkConfig

react_config = FrameworkConfig(
    id="react",
    displayName="React",
    languages=["typescript", "javascript"],
    detectionKeywords=["react", "react-dom", "@types/react"],
    manifestFiles=["package.json"],
    promptSnippetPath="./frameworks/react.md",
    entryPoints=[
        "src/App.tsx",
        "src/App.jsx",
        "src/index.tsx",
        "src/main.tsx",
    ],
    layerHints={
        "components": "ui",
        "hooks": "service",
        "pages": "ui",
        "contexts": "service",
        "utils": "utility",
        "lib": "service",
    },
)
