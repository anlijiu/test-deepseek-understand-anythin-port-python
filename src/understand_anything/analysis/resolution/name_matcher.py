"""符号名称匹配器 — 支持精确、限定名、方法调用模式、模糊匹配.

提供四级匹配策略, 每级返回置信度评分 0.0-1.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.analysis.resolution.types import ResolutionContext


def match_exact(
    symbol: str, candidates: set[str]
) -> list[tuple[str, float]]:
    """精确名称匹配 — 置信度 0.95.

    Args:
        symbol: 要匹配的符号名.
        candidates: 候选符号名集合.

    Returns:
        ``[(匹配名, 0.95), ...]`` 或空列表.
    """
    if symbol in candidates:
        return [(symbol, 0.95)]
    return []


def match_qualified(
    symbol: str, candidates: set[str]
) -> list[tuple[str, float]]:
    """限定名匹配 — 置信度 0.8-0.9.

    处理 ``module.Symbol`` 形式: 先尝试完整匹配, 再尝试尾部匹配.

    Args:
        symbol: 带限定路径的符号名.
        candidates: 候选符号名集合.

    Returns:
        ``[(匹配名, 置信度), ...]`` 或空列表.
    """
    results: list[tuple[str, float]] = []

    # Full qualified name match
    if "." in symbol:
        if symbol in candidates:
            results.append((symbol, 0.9))

        # Last segment match (e.g., "os.path" → "path")
        segments = symbol.split(".")
        last = segments[-1]
        if last in candidates:
            results.append((last, 0.85))

        # Try penultimate segment too
        if len(segments) >= 2:
            penultimate = segments[-2]
            if penultimate in candidates:
                results.append((penultimate, 0.5))

    # :: qualified name (C++, Rust)
    if "::" in symbol:
        if symbol in candidates:
            results.append((symbol, 0.9))
        last = symbol.rsplit("::", 1)[-1]
        if last in candidates:
            results.append((last, 0.8))

    return results


def match_method_call(
    symbol: str, candidates: set[str]
) -> list[tuple[str, float]]:
    """对象方法调用模式匹配 — 置信度 0.6-0.8.

    处理 ``obj.method`` 形式, 尝试匹配 ``method`` 部分.

    Args:
        symbol: 对象方法格式符号名.
        candidates: 候选符号名集合.

    Returns:
        ``[(匹配名, 置信度), ...]`` 或空列表.
    """
    results: list[tuple[str, float]] = []

    if "." in symbol:
        # Extract method name after the last dot
        parts = symbol.split(".")
        method_name = parts[-1] if len(parts) > 1 else ""

        # Don't match common invocations like self.method or this.method
        if (
            method_name
            and parts[0]
            not in ("self", "this", "cls", "super", "__class__")
            and method_name in candidates
        ):
            results.append((method_name, 0.7))

        # Also try "obj.method" as a combined match
        if symbol in candidates:
            results.append((symbol, 0.8))

    # method() pattern (just a bare method name)
    if symbol in candidates:
        results.append((symbol, 0.6))

    return results


def match_fuzzy(
    symbol: str, candidates: set[str]
) -> list[tuple[str, float]]:
    """模糊匹配 — 置信度 0.3-0.5.

    尝试:
      1. 大小写不敏感匹配 (置信度 0.5)
      2. snake_case ↔ camelCase 转换匹配 (置信度 0.4)
      3. 前缀匹配 (置信度 0.35)
      4. 子串匹配 (置信度 0.3, 仅对长度 ≥ 4 的符号)

    Args:
        symbol: 要匹配的符号名.
        candidates: 候选符号名集合.

    Returns:
        ``[(匹配名, 置信度), ...]`` 或空列表.
    """
    results: list[tuple[str, float]] = []

    lower = symbol.lower()

    for cand in candidates:
        cand_lower = cand.lower()

        # Case insensitive match
        if lower == cand_lower:
            results.append((cand, 0.5))
            continue

        # snake_case ↔ camelCase conversion
        if lower.replace("_", "") == cand_lower.replace("_", ""):
            results.append((cand, 0.4))
            continue

        # Prefix match (minimum 3 chars)
        if len(symbol) >= 3 and cand_lower.startswith(lower):
            results.append((cand, 0.35))
            continue

        # Substring match (minimum 4 chars)
        if len(symbol) >= 4 and symbol.lower() in cand_lower:
            results.append((cand, 0.3))
            continue

    # Sort by confidence descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def resolve_symbol_name(
    symbol: str,
    candidates: set[str],
    *,
    ref_type: str = "call",
) -> list[tuple[str, float]]:
    """四级综合匹配: 精确 → 限定名 → 方法调用 → 模糊.

    合并所有层级的结果, 去重取最高置信度.

    Args:
        symbol: 原始符号名 (可能包含限定路径).
        candidates: 所有候选符号名.
        ref_type: 引用类型 ("import", "call", "inheritance", "type_ref").

    Returns:
        按置信度降序排列的匹配列表.
    """
    if not symbol or not candidates:
        return []

    all_results: dict[str, float] = {}

    def _add(sym: str, conf: float) -> None:
        if sym not in all_results or conf > all_results[sym]:
            all_results[sym] = conf

    # Level 1: exact match
    for sym, conf in match_exact(symbol, candidates):
        _add(sym, conf)

    # Level 2: qualified name match
    for sym, conf in match_qualified(symbol, candidates):
        _add(sym, conf)

    # Level 3: method call pattern
    if ref_type == "call":
        for sym, conf in match_method_call(symbol, candidates):
            _add(sym, conf)

    # Level 4: fuzzy match (only if nothing found yet, or for type_ref)
    if not all_results or ref_type in ("type_ref", "inheritance"):
        for sym, conf in match_fuzzy(symbol, candidates):
            _add(sym, conf)

    # Return sorted by confidence
    return sorted(all_results.items(), key=lambda x: x[1], reverse=True)


def filter_candidates_by_file(
    symbol: str, ctx: ResolutionContext, source_file: str | None = None
) -> dict[str, set[str]]:
    """构建候选符号的 文件路径 → 符号名集合 映射.

    优先从 export_map 获取, 其次从 symbol_map 获取.

    Args:
        symbol: 要查找的符号名.
        ctx: 解析上下文.
        source_file: 来源文件路径 (用于排除自身).

    Returns:
        ``{file_path: {symbol_name, ...}, ...}`` 映射.
    """
    result: dict[str, set[str]] = {}

    # First collect from symbol_map
    entries = ctx.symbol_map.get(symbol, [])
    for file_path, _kind in entries:
        if file_path != source_file:
            if file_path not in result:
                result[file_path] = set()
            result[file_path].add(symbol)

    # Then enrich from export_map
    for file_path, exports in ctx.export_map.items():
        if file_path == source_file:
            continue
        # Check if the symbol matches any export (exact or case-insensitive)
        if symbol in exports:
            if file_path not in result:
                result[file_path] = set()
            result[file_path].add(symbol)
        else:
            # Case insensitive check
            for exp in exports:
                if exp.lower() == symbol.lower():
                    if file_path not in result:
                        result[file_path] = set()
                    result[file_path].add(exp)

    return result
