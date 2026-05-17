"""导入路径解析 + 重导出链追踪.

将导入源 (e.g. ``"../utils/helpers"``) 解析为项目中的实际文件路径,
并追踪重导出链 (depth 8) 以找到原始导出位置.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.analysis.resolution.types import ResolutionContext


# 各语言的常见扩展名顺序 (优先匹配)
_EXTENSIONS_BY_LANG: dict[str, list[str]] = {
    "python": [".py", ".pyi", ".pyx"],
    "typescript": [".ts", ".tsx", ".mts", ".cts", ".d.ts"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"],
    "c": [".c", ".h"],
    "java": [".java"],
    "go": [".go"],
    "rust": [".rs"],
}


def resolve_import_to_file(
    import_source: str,
    source_file: str,
    ctx: ResolutionContext,
    *,
    language_id: str | None = None,
) -> str | None:
    """将导入语句中的源路径解析为项目中的实际文件.

    策略:
      1. 精确文件匹配
      2. 相对路径解析 (相对于 source_file)
      3. 扩展名补全 (.py, .ts, .js, ...)
      4. 包索引文件 (__init__.py, index.ts 等)

    Args:
        import_source: 导入语句中的源路径 (e.g. ``"../utils/helpers"``).
        source_file: 导入语句所在的文件路径.
        ctx: 解析上下文.
        language_id: 源文件语言 ID (用于选择扩展名).

    Returns:
        相对于 workspace_root 的文件路径, 或 ``None``.
    """
    if not import_source:
        return None

    # 过滤裸内置模块导入 (不含路径分隔符)
    if "/" not in import_source and "." not in import_source.replace("-", ""):
        # 类似 "os", "fs" 之类的裸模块名, 不是相对路径, 跳过文件解析
        pass

    workspace = Path(ctx.workspace_root)
    source_dir = workspace / Path(source_file).parent

    # 选择语言相关的扩展名列表
    extensions = _EXTENSIONS_BY_LANG.get(language_id or "", [])
    if not extensions:
        # 合并所有扩展名
        extensions = []
        for exts in _EXTENSIONS_BY_LANG.values():
            extensions.extend(exts)
        extensions = list(dict.fromkeys(extensions))  # 去重保序

    candidates: list[str] = []

    # 把点分隔符转换为路径分隔符 (Python/Java 风格)
    has_dots = "." in import_source and "/" not in import_source
    if has_dots and language_id in ("python", "java"):
        dot_path = import_source.replace(".", "/")
        candidates.append(dot_path)

    candidates.append(import_source)

    for candidate in candidates:
        # 1. 尝试精确文件匹配
        exact_file = str(workspace / candidate)
        rel_exact = _to_relative(exact_file, workspace)
        if rel_exact in ctx.analyzed_files:
            return rel_exact

        # 2. 尝试相对路径解析
        resolved = _resolve_relative(candidate, source_dir, workspace)
        if resolved and resolved in ctx.analyzed_files:
            return resolved

        # 3. 扩展名补全
        for ext in extensions:
            full = str(workspace / (candidate + ext))
            rel_full = _to_relative(full, workspace)
            if rel_full in ctx.analyzed_files:
                return rel_full

            # Also try relative with extension
            if not candidate.startswith("/"):
                rel_resolved = _resolve_relative(
                    candidate + ext, source_dir, workspace
                )
                if rel_resolved and rel_resolved in ctx.analyzed_files:
                    return rel_resolved

        # 4. 包索引文件
        for index_file in _INDEX_FILES:
            full = str(workspace / candidate / index_file)
            rel_full = _to_relative(full, workspace)
            if rel_full in ctx.analyzed_files:
                return rel_full

    return None


# 包索引文件名
_INDEX_FILES = [
    "__init__.py",
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
    "mod.rs",
    "mod.go",
]


def _to_relative(full_path: str, workspace: Path) -> str:
    """将绝对路径转为相对于 workspace 的路径."""
    try:
        return str(Path(full_path).relative_to(workspace))
    except ValueError:
        return full_path


def _resolve_relative(
    import_source: str, source_dir: Path, workspace: Path
) -> str | None:
    """解析相对导入路径."""
    candidate = source_dir / import_source
    try:
        resolved = candidate.resolve()
        rel = resolved.relative_to(workspace)
        return str(rel)
    except (ValueError, OSError):
        return None


def trace_reexport_chain(
    symbol: str,
    source_file: str,
    ctx: ResolutionContext,
    *,
    max_depth: int = 8,
    language_id: str | None = None,
) -> tuple[str, str] | None:
    """追踪重导出链, 找到符号的原始文件.

    例如: ``a.ts`` 中 ``export { Foo } from './b'``, 而 ``b.ts``
    中 ``export { Foo } from './c'``, ``c.ts`` 定义 ``Foo``.

    Args:
        symbol: 要追踪的符号名.
        source_file: 起始文件.
        ctx: 解析上下文.
        max_depth: 最大追踪深度 (默认 8).
        language_id: 语言 ID.

    Returns:
        ``(最终文件路径, 最终符号名)`` 或 ``None``.
    """
    visited: set[str] = {source_file}
    current_file = source_file
    current_symbol = symbol

    for _ in range(max_depth):
        # 检查当前文件的 export 中是否有重导出 (路径包含 . 或 /)
        exports = ctx.export_map.get(current_file, set())
        if current_symbol not in exports:
            # 当前符号在当前文件, 不再追踪
            return (current_file, current_symbol)

        # 检查是否有来自其他文件的导入 (import_map)
        import_mappings = ctx.import_map.get(current_file, {})
        if not import_mappings:
            # 没有进一步的导入映射, 当前文件即为源
            return (current_file, current_symbol)

        # 查找重导出目标
        # 通过 export map + import map 推断重导出链
        found_next = False
        for target_file in import_mappings.values():
            if target_file in visited:
                continue
            # 检查目标文件是否导出了该符号
            target_exports = ctx.export_map.get(target_file, set())
            if current_symbol in target_exports:
                visited.add(target_file)
                current_file = target_file
                found_next = True
                break

        if not found_next:
            return (current_file, current_symbol)

    return (current_file, current_symbol)
