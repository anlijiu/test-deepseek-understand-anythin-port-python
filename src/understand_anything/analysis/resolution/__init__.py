"""跨文件引用解析子系统.

提供 ``ReferenceResolver`` 协调器, 将四种解析策略
(框架 → 导入 → 名称匹配 → 模糊) 串联执行.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from understand_anything.analysis.resolution.builtins import is_builtin
from understand_anything.analysis.resolution.import_resolver import (
    resolve_import_to_file,
    trace_reexport_chain,
)
from understand_anything.analysis.resolution.name_matcher import (
    filter_candidates_by_file,
    resolve_symbol_name,
)
from understand_anything.analysis.resolution.types import (
    ResolutionContext,
    ResolvedRef,
    UnresolvedRef,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 边类型自动提升规则
# ---------------------------------------------------------------------------

# 引用类型 → 边类型映射 (当 confidence ≥ 0.7 时提升边的语义)
_REF_TYPE_TO_EDGE: dict[str, str] = {
    "import": "imports",
    "call": "calls",
    "inheritance": "inherits",
    "type_ref": "references",
}


class ReferenceResolver:
    """跨文件引用解析协调器.

    执行四级解析策略:
      1. **框架解析**: 由框架感知的导入映射提供 (外部注入).
      2. **导入解析**: 从 import 语句解析文件路径 → 匹配导出符号.
      3. **名称匹配**: 从全局符号表匹配 (精确/限定名/方法调用).
      4. **模糊匹配**: 大小写不敏感 / snake↔camel / 前缀/子串.

    属性:
        ctx: 全局解析上下文.
        framework_mappings: 框架感知的解析结果 (外部注入).
    """

    def __init__(self, ctx: ResolutionContext) -> None:
        """初始化解析器.

        Args:
            ctx: 包含文件/导入/导出/符号索引的上下文.
        """
        self.ctx = ctx
        self.framework_mappings: dict[
            str, list[ResolvedRef]
        ] = {}  # source_file -> resolved refs

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def resolve(
        self,
        unresolved: list[UnresolvedRef],
        *,
        language_id: str | None = None,
    ) -> list[ResolvedRef]:
        """解析一批未解析引用.

        Args:
            unresolved: 待解析的引用列表.
            language_id: 当前文件的语言 ID (用于内置过滤).

        Returns:
            已解析引用列表 (仅包含确定性高置信度 ≥ 0.9 的结果).
            第一版不做模糊匹配写入.
        """
        resolved: list[ResolvedRef] = []

        for ref in unresolved:
            result = self._resolve_one(ref, language_id=language_id)
            if result and result.confidence >= 0.9:
                resolved.append(result)

        return resolved

    def resolve_all(
        self,
        all_unresolved: dict[str, list[UnresolvedRef]],
        *,
        language_map: dict[str, str] | None = None,
    ) -> list[ResolvedRef]:
        """批量解析所有文件中的未解析引用.

        Args:
            all_unresolved: ``{file_path: [UnresolvedRef, ...]}``.
            language_map: ``{file_path: language_id}``.

        Returns:
            所有已解析引用的合并列表 (已去重).
        """
        all_resolved: list[ResolvedRef] = []
        seen: set[tuple[str, str, str]] = set()  # (source, symbol, target)

        for file_path, refs in all_unresolved.items():
            lang = (language_map or {}).get(file_path)
            resolved = self.resolve(refs, language_id=lang)
            for r in resolved:
                key = (
                    r.unresolved.source_file,
                    r.unresolved.symbol,
                    r.target_file,
                )
                if key not in seen:
                    seen.add(key)
                    all_resolved.append(r)

        return all_resolved

    # ------------------------------------------------------------------
    # 单条解析
    # ------------------------------------------------------------------

    def _resolve_one(
        self,
        ref: UnresolvedRef,
        *,
        language_id: str | None = None,
    ) -> ResolvedRef | None:
        """对单条引用执行确定性解析 (v2: 仅 import-based, 不做 fuzzy).

        返回第一个高置信度匹配. 不启用模糊策略.
        """

        # 过滤内置符号
        if is_builtin(ref.symbol, language_id):
            return None

        # 策略 1: 框架感知解析 (外部注入)
        fw_result = self._resolve_framework(ref)
        if fw_result and fw_result.confidence >= 0.9:
            return fw_result

        # 策略 2: 导入解析 (确定性)
        imp_result = self._resolve_import(ref, language_id=language_id)
        if imp_result and imp_result.confidence >= 0.9:
            return imp_result

        # 策略 3: 名称匹配 (仅精确匹配, confidence ≥ 0.95)
        name_result = self._resolve_by_name(ref)
        if name_result and name_result.confidence >= 0.95:
            return name_result

        # v2: 不做模糊匹配, 低置信度结果返回 None
        return None

    # ------------------------------------------------------------------
    # 策略实现
    # ------------------------------------------------------------------

    def _resolve_framework(self, ref: UnresolvedRef) -> ResolvedRef | None:
        """策略 1: 框架感知解析."""
        source_refs = self.framework_mappings.get(ref.source_file, [])
        for resolved in source_refs:
            if resolved.unresolved.symbol == ref.symbol:
                return resolved
        return None

    def _resolve_import(
        self,
        ref: UnresolvedRef,
        *,
        language_id: str | None = None,
    ) -> ResolvedRef | None:
        """策略 2: 导入路径解析.

        从 import_source 解析目标文件, 然后匹配导出符号.
        """
        if not ref.import_source:
            return None

        target_file = resolve_import_to_file(
            ref.import_source,
            ref.source_file,
            self.ctx,
            language_id=language_id,
        )
        if target_file is None:
            return None

        # 追踪重导出链
        chain = trace_reexport_chain(
            ref.symbol,
            target_file,
            self.ctx,
            language_id=language_id,
        )
        if chain:
            final_file, final_symbol = chain
        else:
            final_file = target_file
            final_symbol = ref.symbol

        return ResolvedRef(
            unresolved=ref,
            target_file=final_file,
            target_symbol=final_symbol,
            confidence=0.9,
            edge_type_hint=_REF_TYPE_TO_EDGE.get(
                ref.ref_type, "references"
            ),
            resolution_strategy="import_resolution",
        )

    def _resolve_by_name(self, ref: UnresolvedRef) -> ResolvedRef | None:
        """策略 3: 全局名称匹配.

        从所有已分析文件中的符号表匹配.
        """
        # Collect all candidate symbols
        all_candidates: set[str] = set()
        for exports in self.ctx.export_map.values():
            all_candidates.update(exports)
        # Also from symbol_map — use keys (symbol names), not entry tuples
        for symbol_name, entries in self.ctx.symbol_map.items():
            if any(
                kind in ("function", "class", "variable")
                for _, kind in entries
            ):
                all_candidates.add(symbol_name)

        matches = resolve_symbol_name(
            ref.symbol, all_candidates, ref_type=ref.ref_type
        )
        if not matches:
            return None

        # Find which file the best match belongs to
        best_name, best_conf = matches[0]
        candidates_by_file = filter_candidates_by_file(
            best_name, self.ctx, source_file=ref.source_file
        )
        if not candidates_by_file:
            return None

        # Pick the first file with the symbol
        target_file = next(iter(candidates_by_file.keys()))

        return ResolvedRef(
            unresolved=ref,
            target_file=target_file,
            target_symbol=best_name,
            confidence=best_conf,
            edge_type_hint=_REF_TYPE_TO_EDGE.get(
                ref.ref_type, "references"
            ),
            resolution_strategy=f"name_match({best_name}:{best_conf:.2f})",
        )

    def _resolve_fuzzy(self, ref: UnresolvedRef) -> ResolvedRef | None:
        """策略 4: 模糊匹配 (大小写不敏感等)."""
        all_candidates: set[str] = set()
        for exports in self.ctx.export_map.values():
            all_candidates.update(exports)

        from understand_anything.analysis.resolution.name_matcher import (
            match_fuzzy,
        )

        matches = match_fuzzy(ref.symbol, all_candidates)
        if not matches:
            return None

        best_name, best_conf = matches[0]
        if best_conf < 0.3:
            return None

        candidates_by_file = filter_candidates_by_file(
            best_name, self.ctx, source_file=ref.source_file
        )
        if not candidates_by_file:
            return None

        target_file = next(iter(candidates_by_file.keys()))

        return ResolvedRef(
            unresolved=ref,
            target_file=target_file,
            target_symbol=best_name,
            confidence=best_conf,
            edge_type_hint="references",
            resolution_strategy=f"fuzzy_match({best_name}:{best_conf:.2f})",
        )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def build_resolution_context(
    *,
    workspace_root: str,
    analyzed_files: set[str],
    import_map: dict[str, dict[str, str]],
    export_map: dict[str, set[str]],
    symbol_map: dict[str, list[tuple[str, str]]] | None = None,
) -> ResolutionContext:
    """构建 ``ResolutionContext``.

    Args:
        workspace_root: 项目根目录.
        analyzed_files: 已分析文件路径集合.
        import_map: ``{file: {import_source: target_file}}``.
        export_map: ``{file: {exported_name}}``.
        symbol_map: ``{symbol_name: [(file, kind)]}`` (可选).

    Returns:
        ``ResolutionContext`` 实例.
    """
    return ResolutionContext(
        workspace_root=workspace_root,
        analyzed_files=analyzed_files,
        import_map=import_map,
        export_map=export_map,
        symbol_map=symbol_map or {},
    )


__all__ = [
    "ReferenceResolver",
    "ResolutionContext",
    "ResolvedRef",
    "UnresolvedRef",
    "build_resolution_context",
]
