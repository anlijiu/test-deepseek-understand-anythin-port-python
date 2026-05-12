"""语言注册表 — 扩展名/文件名到语言配置的映射。

Python port of the TypeScript ``LanguageRegistry`` from
``@understand-anything/core/src/languages/language-registry.ts``.
"""

from __future__ import annotations

from understand_anything.languages.types import LanguageConfig


class LanguageRegistry:
    """管理语言配置的注册表。

    Maintains three internal indexes:
    - ``by_id``: 语言 ID → LanguageConfig
    - ``by_extension``: 扩展名 → LanguageConfig
    - ``by_filename``: 文件名 → LanguageConfig

    文件检测时，文件名匹配优先于扩展名匹配（更精确）。
    """

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._by_id: dict[str, LanguageConfig] = {}
        self._by_extension: dict[str, LanguageConfig] = {}
        self._by_filename: dict[str, LanguageConfig] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, config: LanguageConfig) -> None:
        """注册一个语言配置。

        将配置同时索引到 ``by_id``、``by_extension`` 和 ``by_filename`` 映射中。
        扩展名自动规范化为带前导点的小写形式。

        Args:
            config: 要注册的 ``LanguageConfig``。
        """
        self._by_id[config.id] = config

        for ext in config.extensions:
            key = ext if ext.startswith(".") else f".{ext}"
            self._by_extension[key.lower()] = config

        if config.filenames:
            for filename in config.filenames:
                self._by_filename[filename.lower()] = config

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_by_id(self, id_str: str) -> LanguageConfig | None:
        """按语言 ID 查找配置。

        Args:
            id_str: 语言标识符，如 ``"python"``。

        Returns:
            匹配的 ``LanguageConfig``，未找到返回 ``None``。
        """
        return self._by_id.get(id_str)

    def get_by_extension(self, ext: str) -> LanguageConfig | None:
        """按扩展名查找配置。

        自动规范化为带前导点的小写形式。

        Args:
            ext: 文件扩展名，如 ``".py"`` 或 ``"py"``。

        Returns:
            匹配的 ``LanguageConfig``，未找到返回 ``None``。
        """
        key = ext if ext.startswith(".") else f".{ext}"
        return self._by_extension.get(key.lower())

    def get_by_filename(self, filename: str) -> LanguageConfig | None:
        """按精确文件名查找配置（大小写不敏感）。

        Args:
            filename: 文件名，如 ``"Dockerfile"``、``"Makefile"``。

        Returns:
            匹配的 ``LanguageConfig``，未找到返回 ``None``。
        """
        return self._by_filename.get(filename.lower())

    def get_for_file(self, file_path: str) -> LanguageConfig | None:
        """检测文件路径对应的语言配置。

        检测顺序：
        1. 文件名精确匹配（优先，处理 Dockerfile、Makefile 等无扩展名文件）。
        2. 扩展名匹配（回退）。

        Args:
            file_path: 文件路径（绝对或相对）。

        Returns:
            匹配的 ``LanguageConfig``，未识别则返回 ``None``。
        """
        # Extract basename for filename-based matching
        basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

        # 1. Filename match first (more specific)
        filename_match = self._by_filename.get(basename.lower())
        if filename_match is not None:
            return filename_match

        # 2. Fall back to extension match
        last_dot = file_path.rfind(".")
        if last_dot == -1:
            return None
        ext = file_path[last_dot:].lower()
        return self._by_extension.get(ext)

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def get_all_languages(self) -> list[LanguageConfig]:
        """返回所有已注册语言配置的列表。

        Returns:
            ``LanguageConfig`` 列表，按注册顺序排列。
        """
        return list(self._by_id.values())

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def create_default() -> LanguageRegistry:
        """创建预填充所有内置语言配置的注册表。

        Returns:
            包含所有内置 ``LanguageConfig`` 的 ``LanguageRegistry`` 实例。
        """
        from understand_anything.languages.configs import builtin_language_configs

        registry = LanguageRegistry()
        for config in builtin_language_configs:
            registry.register(config)
        return registry
