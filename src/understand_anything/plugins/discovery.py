"""Plugin discovery and configuration parsing.

Python port of the TypeScript plugin discovery from
``@understand-anything/core/src/plugins/discovery.ts``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class PluginEntry:
    """单个插件的配置条目。

    Attributes:
        name: 插件名称，如 ``"tree-sitter"``。
        enabled: 是否启用，默认 ``True``。
        languages: 该插件处理的语言 ID 列表。
        options: 可选的插件特定选项字典。
    """

    name: str
    """插件名称。"""

    languages: list[str]
    """该插件处理的语言 ID 列表。"""

    enabled: bool = True
    """是否启用此插件。"""

    options: dict[str, Any] | None = None
    """插件特定选项（可选）。"""


@dataclass
class PluginConfig:
    """插件配置的顶层容器。

    Attributes:
        plugins: ``PluginEntry`` 列表。
    """

    plugins: list[PluginEntry]
    """插件条目列表。"""


def _build_default_config() -> PluginConfig:
    """构建默认插件配置 — 启用 tree-sitter 插件用于所有支持的语言。

    以 TreeSitterPlugin 实际注册的 extractor 列表为准，
    而非 LanguageConfig 中是否声明了 treeSitter 字段。
    避免"配置说支持、运行时不支持"的假阳性。
    """
    from understand_anything.plugins.tree_sitter import (
        SUPPORTED_TREE_SITTER_LANGUAGES,
    )

    return PluginConfig(
        plugins=[
            PluginEntry(
                name="tree-sitter",
                enabled=True,
                languages=list(SUPPORTED_TREE_SITTER_LANGUAGES),
            ),
        ],
    )


DEFAULT_PLUGIN_CONFIG: PluginConfig = _build_default_config()
"""默认插件配置 — 启用 tree-sitter 插件用于所有带 tree-sitter 语法的语言。"""


def _copy_default_plugin_config() -> PluginConfig:
    """返回默认插件配置的深拷贝，避免调用方污染全局默认配置。

    Returns:
        默认配置的深拷贝。
    """
    return PluginConfig(
        plugins=[
            PluginEntry(
                name=entry.name,
                enabled=entry.enabled,
                languages=list(entry.languages),
                options=dict(entry.options) if entry.options is not None else None,
            )
            for entry in DEFAULT_PLUGIN_CONFIG.plugins
        ]
    )


def parse_plugin_config(json_string: str) -> PluginConfig:
    """从 JSON 字符串解析插件配置。

    解析失败或格式不正确时返回默认配置。

    Args:
        json_string: 插件配置的 JSON 字符串。

    Returns:
        解析后的 ``PluginConfig``，或默认配置。
    """
    if not json_string.strip():
        return _copy_default_plugin_config()

    try:
        parsed = json.loads(json_string)
    except json.JSONDecodeError:
        return _copy_default_plugin_config()

    if not isinstance(parsed, dict) or not isinstance(parsed.get("plugins"), list):
        return _copy_default_plugin_config()

    entries: list[PluginEntry] = []
    for entry in parsed["plugins"]:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        languages = entry.get("languages")

        # Validate required fields
        if not isinstance(name, str) or len(name) == 0:
            continue
        if not isinstance(languages, list) or len(languages) == 0:
            continue

        # Filter out non-string or empty string elements
        languages = [lang for lang in languages if isinstance(lang, str) and len(lang) > 0]
        if len(languages) == 0:
            continue

        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = True

        options = entry.get("options")
        if options is not None and not isinstance(options, dict):
            options = None

        entries.append(
            PluginEntry(
                name=name,
                enabled=enabled,
                languages=languages,
                options=options,
            )
        )

    return PluginConfig(plugins=entries)


def serialize_plugin_config(config: PluginConfig) -> str:
    """将插件配置序列化为格式化的 JSON 字符串。

    Args:
        config: 要序列化的 ``PluginConfig``。

    Returns:
        格式化的 JSON 字符串（indent=2）。
    """
    plugins_data: list[dict[str, Any]] = []
    for entry in config.plugins:
        data: dict[str, Any] = {
            "name": entry.name,
            "enabled": entry.enabled,
            "languages": entry.languages,
        }
        if entry.options is not None:
            data["options"] = entry.options
        plugins_data.append(data)

    return json.dumps({"plugins": plugins_data}, indent=2, ensure_ascii=False)
