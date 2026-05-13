"""框架注册表 — 从清单文件内容检测框架。

Python port of the TypeScript ``FrameworkRegistry`` from
``@understand-anything/core/src/languages/framework-registry.ts``.

Manifest-type-specific structural parsing replaces bare substring matching
to eliminate false positives (e.g. "preact" falsely matching "react").
"""

from __future__ import annotations

import configparser
import functools
import json
import re
import sys
from typing import TYPE_CHECKING

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]  # ty: ignore[unresolved-import]

if TYPE_CHECKING:
    from collections.abc import Callable

    from understand_anything.languages.types import FrameworkConfig


# ------------------------------------------------------------------
# Manifest parser functions
# ------------------------------------------------------------------


def _parse_package_json(content: str) -> set[str]:
    """Parse a ``package.json`` string and return the set of dependency names.

    Collects keys from all standard dependency sections:
    ``dependencies``, ``devDependencies``, ``peerDependencies``,
    ``optionalDependencies``.

    Args:
        content: Raw ``package.json`` file text.

    Returns:
        Set of lowercase dependency package names.  Returns an empty set on
        parse errors.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return set()

    names: set[str] = set()
    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        deps = data.get(section)
        if isinstance(deps, dict):
            for key in deps:
                names.add(key.lower())
    return names


def _parse_requirements_txt(content: str) -> set[str]:
    """Parse a ``requirements.txt`` string and return the set of package names.

    Extracts package names before any version specifiers (``==``, ``>=``,
    ``<=``, ``!=``, ``~=``, ``>``, ``<``, ``[`` extras, or ``;`` markers).
    Skips comments, blank lines, ``-r`` includes, ``-e`` editable installs,
    and ``--`` options.

    Args:
        content: Raw ``requirements.txt`` file text.

    Returns:
        Set of lowercase package names.
    """
    names: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("-r ", "-e ", "--")):
            continue
        # Remove inline comments (rough: everything after " #" but not in strings)
        if " #" in stripped:
            stripped = stripped[: stripped.index(" #")]
        # Extract package name before any version/extras/marker delimiter
        m = re.match(
            r"^[\w][\w.\-]*",
            stripped,
        )
        if m:
            names.add(m.group().lower())
    return names


def _extract_pep508_name(req: str) -> str | None:
    """Extract the package name from a PEP 508 dependency string.

    Examples:
        ``"django>=4.2"`` → ``"django"``
        ``"fastapi[all]>=0.100.0"`` → ``"fastapi"``
        ``"requests ; python_version >= '3.8'"`` → ``"requests"``

    Args:
        req: A PEP 508 dependency specification string.

    Returns:
        Lowercase package name, or ``None`` if extraction fails.
    """
    m = re.match(r"^[\w][\w.\-]*", req.strip())
    if m:
        return m.group().lower()
    return None


def _parse_pyproject_toml(content: str) -> set[str]:
    """Parse a ``pyproject.toml`` string and return the set of dependency names.

    Reads from ``project.dependencies`` (list of PEP 508 strings) and
    ``project.optional-dependencies`` (dict of lists).

    Args:
        content: Raw ``pyproject.toml`` file text.

    Returns:
        Set of lowercase package names.  Returns an empty set on parse errors.
    """
    try:
        data = tomllib.loads(content)
    except Exception:
        return set()

    names: set[str] = set()
    project = data.get("project")
    if isinstance(project, dict):
        deps = project.get("dependencies")
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str):
                    name = _extract_pep508_name(dep)
                    if name:
                        names.add(name)

        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for dep_list in optional.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        if isinstance(dep, str):
                            name = _extract_pep508_name(dep)
                            if name:
                                names.add(name)

    # Also try tool.poetry.dependencies (Poetry format)
    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            poetry_deps = poetry.get("dependencies")
            if isinstance(poetry_deps, dict):
                for key in poetry_deps:
                    if key.lower() != "python":
                        names.add(key.lower())

    return names


def _parse_pipfile(content: str) -> set[str]:
    """Parse a ``Pipfile`` (TOML) string and return the set of dependency names.

    Reads keys from the ``[packages]`` and ``[dev-packages]`` sections.

    Args:
        content: Raw ``Pipfile`` text.

    Returns:
        Set of lowercase package names.  Returns an empty set on parse errors.
    """
    try:
        data = tomllib.loads(content)
    except Exception:
        return set()

    names: set[str] = set()
    for section in ("packages", "dev-packages"):
        deps = data.get(section)
        if isinstance(deps, dict):
            for key in deps:
                names.add(key.lower())
    return names


def _parse_setup_cfg(content: str) -> set[str]:
    """Parse a ``setup.cfg`` string and return the set of dependency names.

    Reads from the ``install_requires`` key under the ``[options]`` section.

    Args:
        content: Raw ``setup.cfg`` file text.

    Returns:
        Set of lowercase package names.  Returns an empty set on parse errors.
    """
    try:
        parser = configparser.ConfigParser()
        parser.read_string(content)
    except Exception:
        return set()

    names: set[str] = set()
    if parser.has_option("options", "install_requires"):
        raw = parser.get("options", "install_requires")
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = _extract_pep508_name(line)
            if name:
                names.add(name)
    return names


def _parse_go_mod(content: str) -> set[str]:
    """Parse a ``go.mod`` string and return the set of module paths from
    ``require`` blocks.

    Args:
        content: Raw ``go.mod`` file text.

    Returns:
        Set of lowercase module paths.
    """
    names: set[str] = set()

    # Match single-line require: require module/path v1.2.3
    for m in re.finditer(
        r"^\s*require\s+([\w.\-/%]+)\s+\S",
        content,
        re.MULTILINE,
    ):
        names.add(m.group(1).lower())

    # Match require block: require ( ... )
    block_match = re.search(
        r"require\s*\(([^)]+)\)",
        content,
        re.DOTALL,
    )
    if block_match:
        for m in re.finditer(
            r"^\s*([\w.\-/%]+)\s+",
            block_match.group(1),
            re.MULTILINE,
        ):
            names.add(m.group(1).lower())

    return names


def _parse_gemfile(content: str) -> set[str]:
    """Parse a ``Gemfile`` string and return gem names from ``gem`` directives.

    Matches patterns like ``gem 'rails'``, ``gem "rspec"``, and optional
    version/group arguments.

    Args:
        content: Raw ``Gemfile`` text.

    Returns:
        Set of lowercase gem names.
    """
    names: set[str] = set()
    for m in re.finditer(
        r"""^\s*gem\s+['"]([^'"]+)['"]""",
        content,
        re.MULTILINE,
    ):
        names.add(m.group(1).lower())
    return names


# ------------------------------------------------------------------
# Parser lookup (cached)
# ------------------------------------------------------------------

_PARSER_MAP: dict[str, Callable[[str], set[str]]] = {
    "package.json": _parse_package_json,
    "requirements.txt": _parse_requirements_txt,
    "pyproject.toml": _parse_pyproject_toml,
    "Pipfile": _parse_pipfile,
    "setup.cfg": _parse_setup_cfg,
    "go.mod": _parse_go_mod,
    "Gemfile": _parse_gemfile,
}
"""Mapping from manifest basename to structural parser function.

Manifests not in this map (e.g. ``setup.py``, ``pom.xml``, ``build.gradle``)
fall back to word-boundary regex matching.
"""


@functools.lru_cache(maxsize=32)
def _get_parser(filename: str) -> Callable[[str], set[str]] | None:
    """Return the structural parser for *filename*, or ``None`` for fallback.

    The *filename* is expected to be a basename (e.g. ``"package.json"``).

    Args:
        filename: Manifest basename.

    Returns:
        Parser callable, or ``None`` if no dedicated parser exists.
    """
    return _PARSER_MAP.get(filename)


# ------------------------------------------------------------------
# Fallback word-boundary matcher
# ------------------------------------------------------------------

_FALLBACK_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _fallback_match(keyword: str, content: str) -> bool:
    """Check whether *keyword* appears as a whole word in *content*.

    Used for manifest types without dedicated structural parsers (e.g.
    ``setup.py``, ``pom.xml``, ``build.gradle``).

    Args:
        keyword: The detection keyword to search for.
        content: Raw manifest file text.

    Returns:
        ``True`` if *keyword* matches as a word boundary.
    """
    if keyword not in _FALLBACK_RE_CACHE:
        _FALLBACK_RE_CACHE[keyword] = re.compile(
            rf"\b{re.escape(keyword)}\b",
            re.IGNORECASE,
        )
    return bool(_FALLBACK_RE_CACHE[keyword].search(content))


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

        对每个已注册的框架配置，查找匹配的清单文件并使用**结构解析**
        （而非裸子串匹配）检查 ``detection_keywords``。 这样可消除由子串
        重叠引起的假阳性（例如 ``"preact"`` 错误命中 ``"react"``）。

        解析策略因清单类型而异：

        - ``package.json`` → JSON 解析，提取依赖键
        - ``requirements.txt`` → 逐行提取包名
        - ``pyproject.toml`` → TOML 解析（PEP 508）
        - ``Pipfile`` → TOML 解析，提取键
        - ``setup.cfg`` → ConfigParser
        - ``go.mod`` → 提取 ``require`` 模块路径
        - ``Gemfile`` → 正则提取 gem 名称
        - ``setup.py`` / ``pom.xml`` / ``build.gradle`` → 词边界正则回退

        每种清单仅解析一次（缓存）。

        Args:
            manifests: 文件名 → 文件内容映射，如
                ``{"requirements.txt": "django==4.2\\n...", "package.json": "..."}``。

        Returns:
            检测到的 ``FrameworkConfig`` 列表（去重）。
        """
        detected: set[str] = set()
        results: list[FrameworkConfig] = []

        # Cache parsed package-name sets (keyed by the manifest file key in manifests)
        parsed_cache: dict[str, set[str] | None] = {}

        for config in self._by_id.values():
            if config.id in detected:
                continue

            for manifest_file in config.manifest_files:
                # Match by filename (basename or path-suffix match)
                content: str | None = None
                matched_key: str | None = None
                for key, val in manifests.items():
                    if key == manifest_file or key.endswith(f"/{manifest_file}"):
                        content = val
                        matched_key = key
                        break

                if content is None:
                    continue

                # --- Resolve parsed package names (cached) ---
                parsed: set[str] | None = None
                cache_key = matched_key or manifest_file
                if cache_key in parsed_cache:
                    parsed = parsed_cache[cache_key]
                else:
                    parser = _get_parser(manifest_file)
                    parsed = parser(content) if parser is not None else None  # None → fallback to regex
                    parsed_cache[cache_key] = parsed

                # --- Keyword matching ---
                if parsed is not None:
                    # Structural match: keyword (lowercased) must be in parsed
                    # package names
                    found = any(
                        kw.lower() in parsed
                        for kw in config.detection_keywords
                    )
                else:
                    # Fallback: word-boundary regex for unparseable manifests
                    found = any(
                        _fallback_match(kw, content)
                        for kw in config.detection_keywords
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
