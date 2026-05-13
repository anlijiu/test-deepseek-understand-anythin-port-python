"""内置语言配置聚合 — 40 种语言的完整配置。

Python port of the TypeScript ``configs/index.ts``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from understand_anything.languages.configs.batch import batch_config
from understand_anything.languages.configs.c import c_config
from understand_anything.languages.configs.cpp import cpp_config
from understand_anything.languages.configs.csharp import csharp_config
from understand_anything.languages.configs.css import css_config
from understand_anything.languages.configs.csv import csv_config
from understand_anything.languages.configs.docker_compose import docker_compose_config
from understand_anything.languages.configs.dockerfile import dockerfile_config
from understand_anything.languages.configs.env import env_config
from understand_anything.languages.configs.github_actions import github_actions_config
from understand_anything.languages.configs.go import go_config
from understand_anything.languages.configs.graphql import graphql_config
from understand_anything.languages.configs.html import html_config
from understand_anything.languages.configs.java import java_config
from understand_anything.languages.configs.javascript import javascript_config
from understand_anything.languages.configs.jenkinsfile import jenkinsfile_config
from understand_anything.languages.configs.json_config import json_config
from understand_anything.languages.configs.json_schema import json_schema_config
from understand_anything.languages.configs.kotlin import kotlin_config
from understand_anything.languages.configs.kubernetes import kubernetes_config
from understand_anything.languages.configs.lua import lua_config
from understand_anything.languages.configs.makefile import makefile_config

# Non-code languages
from understand_anything.languages.configs.markdown import markdown_config
from understand_anything.languages.configs.openapi import openapi_config
from understand_anything.languages.configs.php import php_config
from understand_anything.languages.configs.plaintext import plaintext_config
from understand_anything.languages.configs.powershell import powershell_config
from understand_anything.languages.configs.protobuf import protobuf_config

# Code languages
from understand_anything.languages.configs.python import python_config
from understand_anything.languages.configs.restructuredtext import (
    restructuredtext_config,
)
from understand_anything.languages.configs.ruby import ruby_config
from understand_anything.languages.configs.rust import rust_config
from understand_anything.languages.configs.shell import shell_config
from understand_anything.languages.configs.sql import sql_config
from understand_anything.languages.configs.swift import swift_config
from understand_anything.languages.configs.terraform import terraform_config
from understand_anything.languages.configs.toml import toml_config
from understand_anything.languages.configs.typescript import typescript_config
from understand_anything.languages.configs.xml import xml_config
from understand_anything.languages.configs.yaml import yaml_config

if TYPE_CHECKING:
    from understand_anything.languages.types import LanguageConfig

builtin_language_configs: list[LanguageConfig] = [
    # Code languages
    typescript_config,
    javascript_config,
    python_config,
    go_config,
    rust_config,
    java_config,
    ruby_config,
    php_config,
    swift_config,
    kotlin_config,
    lua_config,
    c_config,
    cpp_config,
    csharp_config,
    # Non-code languages
    markdown_config,
    yaml_config,
    json_config,
    toml_config,
    env_config,
    xml_config,
    dockerfile_config,
    sql_config,
    graphql_config,
    protobuf_config,
    terraform_config,
    github_actions_config,
    makefile_config,
    shell_config,
    html_config,
    css_config,
    openapi_config,
    kubernetes_config,
    docker_compose_config,
    json_schema_config,
    csv_config,
    restructuredtext_config,
    powershell_config,
    batch_config,
    jenkinsfile_config,
    plaintext_config,
]
"""所有内置语言配置的列表，按注册优先级排列。"""
