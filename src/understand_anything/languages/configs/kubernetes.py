"""内置语言配置 — Kubernetes。

Python port of the TypeScript ``kubernetesConfig``.

TODO: Kubernetes 清单文件是 YAML，没有唯一扩展名或文件名。
当前无法通过注册表检测（无扩展名、无文件名），需要基于内容的检测。
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

kubernetes_config = LanguageConfig(
    id="kubernetes",
    displayName="Kubernetes",
    extensions=[],
    concepts=[
        "deployments",
        "services",
        "pods",
        "configmaps",
        "secrets",
        "ingress",
        "volumes",
        "namespaces",
    ],
    filePatterns=FilePatternConfig(
        config=["k8s/*.yaml", "kubernetes/*.yaml"],
    ),
)
