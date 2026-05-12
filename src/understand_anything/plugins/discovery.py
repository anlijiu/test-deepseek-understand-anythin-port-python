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
    """构建默认插件配置 — 启用 tree-sitter 插件用于所有支持的语言。"""
    from understand_anything.languages.configs import builtin_language_configs

    tree_sitter_languages = [
        c.id for c in builtin_language_configs if c.tree_sitter is not None
    ]

    return PluginConfig(
        plugins=[
            PluginEntry(
                name="tree-sitter",
                enabled=True,
                languages=tree_sitter_languages,
            ),
        ],
    )


DEFAULT_PLUGIN_CONFIG: PluginConfig = _build_default_config()
"""默认插件配置 — 启用 tree-sitter 插件用于所有带 tree-sitter 语法的语言。"""


def parse_plugin_config(json_string: str) -> PluginConfig:
    """从 JSON 字符串解析插件配置。

    解析失败或格式不正确时返回默认配置。

    Args:
        json_string: 插件配置的 JSON 字符串。

    Returns:
        解析后的 ``PluginConfig``，或默认配置。
    """
    if not json_string.strip():
        return PluginConfig(plugins=list(DEFAULT_PLUGIN_CONFIG.plugins))

    try:
        parsed = json.loads(json_string)
    except json.JSONDecodeError:
        return PluginConfig(plugins=list(DEFAULT_PLUGIN_CONFIG.plugins))

    if not isinstance(parsed, dict) or not isinstance(parsed.get("plugins"), list):
        return PluginConfig(plugins=list(DEFAULT_PLUGIN_CONFIG.plugins))

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
