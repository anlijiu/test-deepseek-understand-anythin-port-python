"""内置语言配置 — Terraform。

Python port of the TypeScript ``terraformConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

terraform_config = LanguageConfig(
    id="terraform",
    displayName="Terraform",
    extensions=[".tf", ".tfvars"],
    concepts=[
        "resources",
        "data sources",
        "variables",
        "outputs",
        "modules",
        "providers",
        "state",
        "workspaces",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["main.tf"],
        config=["terraform.tfvars", "variables.tf"],
    ),
)
