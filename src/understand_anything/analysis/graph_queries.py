"""图查询管理器 — 高层查询接口, 结合遍历和持久化查询."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from understand_anything.analysis.graph_traversal import GraphTraverser

if TYPE_CHECKING:
    from understand_anything.persistence.queries import QueryBuilder
    from understand_anything.types import KnowledgeGraph

logger = logging.getLogger(__name__)


class GraphQueryManager:
    """图查询管理器.

    提供面向用户的高层查询接口:
      - 按类型/名称/文件查找节点
      - 获取调用者和被调用者
      - 查看影响范围
      - 查找文件之间的路径
      - 全文搜索 (需 SQLite 后端)

    Example::

        qm = GraphQueryManager(graph, queries=db.queries)
        callers = qm.callers_of("function:src/main.py:run")
        path = qm.find_path("file:src/a.ts", "file:src/b.ts")
    """

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        queries: QueryBuilder | None = None,
    ) -> None:
        """初始化查询管理器.

        Args:
            graph: 知识图谱 (JSON 内存).
            queries: 查询构建器 (SQLite).
        """
        self._graph = graph
        self._queries = queries
        self._traverser = GraphTraverser(graph=graph, queries=queries)

        # 节点名称索引
        self._name_index: dict[str, list[str]] = {}
        if graph is not None:
            for node in graph.nodes:
                self._name_index.setdefault(node.name, []).append(node.id)

    # ------------------------------------------------------------------
    # 节点查找
    # ------------------------------------------------------------------

    def find_nodes(self, name: str) -> list[str]:
        """按名称查找节点 ID 列表.

        Args:
            name: 节点名称 (精确匹配).

        Returns:
            匹配的节点 ID 列表.
        """
        if self._queries is not None:
            rows = self._queries.get_nodes_by_name(name)
            return [r["id"] for r in rows]
        return self._name_index.get(name, [])

    def nodes_by_type(self, node_type: str) -> list[str]:
        """按类型获取所有节点 ID.

        Args:
            node_type: 节点类型 (e.g. ``"function"``, ``"class"``).

        Returns:
            节点 ID 列表.
        """
        if self._queries is not None:
            return [
                r["id"]
                for r in self._queries.get_nodes_by_type(node_type)
            ]
        if self._graph is not None:
            return [
                node.id
                for node in self._graph.nodes
                if node.type.value == node_type
            ]
        return []

    def get_stats(self) -> dict:
        """获取图统计信息."""
        if self._queries is not None:
            return self._queries.get_stats()
        if self._graph is not None:
            return {
                "node_count": len(self._graph.nodes),
                "edge_count": len(self._graph.edges),
                "layer_count": len(self._graph.layers),
            }
        return {"node_count": 0, "edge_count": 0}

    # ------------------------------------------------------------------
    # 关系查询
    # ------------------------------------------------------------------

    def callers_of(self, node_id: str, *, depth: int = 1) -> list[str]:
        """获取调用者列表.

        Args:
            node_id: 目标节点 ID.
            depth: 搜索深度.

        Returns:
            调用者节点 ID 列表.
        """
        return [
            caller for caller, _ in self._traverser.get_callers(
                node_id, depth=depth
            )
        ]

    def callees_of(self, node_id: str, *, depth: int = 1) -> list[str]:
        """获取被调用者列表.

        Args:
            node_id: 源节点 ID.
            depth: 搜索深度.

        Returns:
            被调用者节点 ID 列表.
        """
        return [
            callee for callee, _ in self._traverser.get_callees(
                node_id, depth=depth
            )
        ]

    def impact_of(
        self, node_id: str, *, depth: int = 2
    ) -> dict[str, list[str]]:
        """获取影响范围.

        Args:
            node_id: 节点 ID.
            depth: 影响深度.

        Returns:
            ``{"direct": [...], "indirect": [...]}``.
        """
        return self._traverser.get_impact(node_id, depth=depth)

    def find_path(
        self, from_id: str, to_id: str, *, max_depth: int = 5
    ) -> list[str] | None:
        """查找两节点间的最短路径.

        Args:
            from_id: 起始节点 ID.
            to_id: 目标节点 ID.
            max_depth: 最大深度.

        Returns:
            路径列表, 或 ``None``.
        """
        return self._traverser.find_path(
            from_id, to_id, max_depth=max_depth
        )

    # ------------------------------------------------------------------
    # 全文搜索
    # ------------------------------------------------------------------

    def search(self, query: str, *, limit: int = 20) -> list[str]:
        """全文搜索 (需 SQLite 后端).

        Args:
            query: 搜索关键词.
            limit: 结果上限.

        Returns:
            匹配的节点 ID 列表.
        """
        if self._queries is not None:
            return [
                r["id"]
                for r in self._queries.search_fts(query, limit=limit)
            ]
        logger.warning("Full-text search requires SQLite backend")
        return []
