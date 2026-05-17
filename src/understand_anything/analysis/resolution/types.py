"""跨文件引用解析的类型定义 (Pydantic models + dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# 解析上下文
# ---------------------------------------------------------------------------


@dataclass
class ResolutionContext:
    """跨文件引用解析所需的全局上下文.

    Attributes:
        workspace_root: 项目根目录的绝对路径.
        analyzed_files: 已分析文件的路径集合 (相对于 workspace_root).
        import_map: 文件路径 → 导入映射 (导入源 → 目标文件路径).
        export_map: 文件路径 → 导出符号名集合.
        symbol_map: 全局符号名 → [(文件路径, 符号类型)] 映射.
    """

    workspace_root: str
    analyzed_files: set[str] = field(default_factory=set)
    import_map: dict[str, dict[str, str]] = field(
        default_factory=dict
    )  # file_path -> {import_source: target_file}
    export_map: dict[str, set[str]] = field(
        default_factory=dict
    )  # file_path -> {exported_name}
    symbol_map: dict[str, list[tuple[str, str]]] = field(
        default_factory=dict
    )  # symbol_name -> [(file_path, kind)]


# ---------------------------------------------------------------------------
# 未解析引用
# ---------------------------------------------------------------------------


@dataclass
class UnresolvedRef:
    """一条未解析的跨文件引用.

    Attributes:
        source_file: 引用来源文件路径.
        symbol: 被引用的符号名 (导入名或调用名, 即 callee).
        ref_type: 引用类型: import, call, inheritance, type_ref.
        line_number: 引用所在行号 (1-based).
        import_source: 如果是 import 引用, 存储 import 的源路径.
        caller_symbol: 如果是 call 引用, 存储调用方函数名 (caller).
    """

    source_file: str
    symbol: str
    ref_type: Literal["import", "call", "inheritance", "type_ref"] = "call"
    line_number: int = 0
    import_source: str = ""
    caller_symbol: str = ""


# ---------------------------------------------------------------------------
# 已解析引用
# ---------------------------------------------------------------------------


@dataclass
class ResolvedRef:
    """一条已解析的跨文件引用.

    Attributes:
        unresolved: 原始未解析引用.
        target_file: 解析到的目标文件路径.
        target_symbol: 解析到的目标符号名 (可能与 symbol 不同, 如 re-export).
        confidence: 置信度 0.0-1.0.
            精确匹配: 0.9+
            导入解析: 0.9
            名称匹配: 0.5-0.7
            模糊匹配: 0.3-0.5
        edge_type_hint: 推荐的边类型, 用于生成图边.
        resolution_strategy: 使用的解析策略描述.
    """

    unresolved: UnresolvedRef
    target_file: str
    target_symbol: str
    confidence: float
    edge_type_hint: str = "references"
    resolution_strategy: str = "unknown"

    def __post_init__(self) -> None:
        """Clamp confidence to [0.0, 1.0]."""
        self.confidence = max(0.0, min(1.0, self.confidence))
