"""内置框架配置 — Vue。

Python port of the TypeScript ``vueConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FrameworkConfig

vue_config = FrameworkConfig(
    id="vue",
    displayName="Vue",
    languages=["typescript", "javascript"],
    detectionKeywords=["vue", "@vue/cli-service", "nuxt", "vite-plugin-vue"],
    manifestFiles=["package.json"],
    promptSnippetPath="./frameworks/vue.md",
    entryPoints=["src/main.ts", "src/App.vue", "src/main.js"],
    layerHints={
        "components": "ui",
        "views": "ui",
        "store": "service",
        "composables": "service",
        "router": "config",
        "plugins": "config",
    },
)
