"""框架注册表 — 从清单文件内容检测框架。

Python port of the TypeScript ``FrameworkRegistry`` from
``@understand-anything/core/src/languages/framework-registry.ts``.
"""

from __future__ import annotations

from understand_anything.languages.types import FrameworkConfig


class FrameworkRegistry:
    """管理框架配置的注册表。

    维护两个内部索引：
    - ``by_id``: 框架 ID → FrameworkConfig
    - ``by_language``: 语言 ID → 该语言可用的 FrameworkConfig 列表

    核心功能是 :meth:`detect_frameworks`，从清单文件内容中自动检测框架。
    """

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._by_id: dict[str, FrameworkConfig] = {}
        self._by_language: dict[str, list[FrameworkConfig]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, config: FrameworkConfig) -> None:
        """注册一个框架配置。

        如果已存在相同 ID 的框架则跳过（幂等）。

        Args:
            config: 要注册的 ``FrameworkConfig``。
        """
        if config.id in self._by_id:
            return

        self._by_id[config.id] = config

        for lang in config.languages:
            existing = self._by_language.get(lang, [])
            existing.append(config)
            self._by_language[lang] = existing

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_by_id(self, id_str: str) -> FrameworkConfig | None:
        """按框架 ID 查找配置。

        Args:
            id_str: 框架标识符，如 ``"django"``、``"react"``。

        Returns:
            匹配的 ``FrameworkConfig``，未找到返回 ``None``。
        """
        return self._by_id.get(id_str)

    def get_for_language(self, lang_id: str) -> list[FrameworkConfig]:
        """获取指定语言可用的所有框架配置。

        Args:
            lang_id: 语言标识符，如 ``"python"``。

        Returns:
            ``FrameworkConfig`` 列表的副本（安全修改）。
        """
        return list(self._by_language.get(lang_id, []))

    def get_all_frameworks(self) -> list[FrameworkConfig]:
        """返回所有已注册框架配置的列表。

        Returns:
            ``FrameworkConfig`` 列表，按注册顺序排列。
        """
        return list(self._by_id.values())

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_frameworks(
        self, manifests: dict[str, str]
    ) -> list[FrameworkConfig]:
        """从清单文件内容中检测框架。

        对于每个注册的框架配置，检查其 ``manifest_files`` 是否存在于
        提供的清单中，如果存在则搜索 ``detection_keywords``（大小写不敏感）。

        Args:
            manifests: 文件名 → 文件内容映射，如
                ``{"requirements.txt": "django==4.2\\n...", "package.json": "..."}``。

        Returns:
            检测到的 ``FrameworkConfig`` 列表（去重）。
        """
        detected: set[str] = set()
        results: list[FrameworkConfig] = []

        for config in self._by_id.values():
            if config.id in detected:
                continue

            for manifest_file in config.manifest_files:
                # Match by filename (basename or path-suffix match)
                content: str | None = None
                for key, val in manifests.items():
                    if key == manifest_file or key.endswith(f"/{manifest_file}"):
                        content = val
                        break

                if content is None:
                    continue

                content_lower = content.lower()
                found = any(
                    keyword.lower() in content_lower
                    for keyword in config.detection_keywords
                )

                if found:
                    detected.add(config.id)
                    results.append(config)
                    break  # Stop checking other manifest files for this config

        return results

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def create_default() -> FrameworkRegistry:
        """创建预填充所有内置框架配置的注册表。

        Returns:
            包含所有内置 ``FrameworkConfig`` 的 ``FrameworkRegistry`` 实例。
        """
        from understand_anything.frameworks import builtin_framework_configs

        registry = FrameworkRegistry()
        for config in builtin_framework_configs:
            registry.register(config)
        return registry
