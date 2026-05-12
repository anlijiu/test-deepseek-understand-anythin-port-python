"""内置框架配置聚合 — 10 种框架的完整配置。

Python port of the TypeScript ``frameworks/index.ts``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from understand_anything.frameworks.django import django_config
from understand_anything.frameworks.express import express_config
from understand_anything.frameworks.fastapi import fastapi_config
from understand_anything.frameworks.flask import flask_config
from understand_anything.frameworks.gin import gin_config
from understand_anything.frameworks.nextjs import nextjs_config
from understand_anything.frameworks.rails import rails_config
from understand_anything.frameworks.react import react_config
from understand_anything.frameworks.spring import spring_config
from understand_anything.frameworks.vue import vue_config

if TYPE_CHECKING:
    from understand_anything.languages.types import FrameworkConfig

builtin_framework_configs: list[FrameworkConfig] = [
    django_config,
    fastapi_config,
    flask_config,
    react_config,
    nextjs_config,
    express_config,
    vue_config,
    spring_config,
    rails_config,
    gin_config,
]
"""所有内置框架配置的列表。"""

__all__ = [
    "builtin_framework_configs",
    "django_config",
    "express_config",
    "fastapi_config",
    "flask_config",
    "gin_config",
    "nextjs_config",
    "rails_config",
    "react_config",
    "spring_config",
    "vue_config",
]
