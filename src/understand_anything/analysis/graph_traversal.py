"""图遍历与路径查找 — BFS/DFS/callers/callees/impact radius/path finding.

支持两种遍历模式:
  - JSON 内存遍历: 直接遍历 KnowledgeGraph Pydantic 模型
  - SQLite 查询遍历: 通过 QueryBuilder 递归 CTE 查询
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.persistence.queries import QueryBuilder
    from understand_anything.types import KnowledgeGraph


class GraphTraverser:
    """知识图谱遍历器.

    提供 BFS/DFS 遍历、callers/callees 查找、影响范围分析和路径查找.

    Example::

        traverser = GraphTraverser(graph)
        callers = traverser.get_callers("function:src/app.py:main")
        impact = traverser.get_impact("function:src/app.py:main", depth=2)
    """

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        queries: QueryBuilder | None = None,
    ) -> None:
        """初始化遍历器.

        Args:
            graph: 知识图谱 (JSON 内存模式).
            queries: 查询构建器 (SQLite 模式). 两者至少提供一个.
        """
        self._graph = graph
        self._queries = queries

        # 内部索引 (从 KnowledgeGraph 构建)
        self._adj_out: dict[str, list[tuple[str, str, float]]] = {}
        # node_id -> [(target_id, edge_type, weight)]
        self._adj_in: dict[str, list[tuple[str, str, float]]] = {}
        # node_id -> [(source_id, edge_type, weight)]

        if graph is not None:
            self._build_index(graph)

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------

    def _build_index(self, graph: KnowledgeGraph) -> None:
        """从 KnowledgeGraph 构建邻接索引."""
        for edge in graph.edges:
            self._adj_out.setdefault(edge.source, []).append(
                (edge.target, edge.type.value, edge.weight)
            )
            self._adj_in.setdefault(edge.target, []).append(
                (edge.source, edge.type.value, edge.weight)
            )

    # ------------------------------------------------------------------
    # BFS / DFS
    # ------------------------------------------------------------------

    def bfs(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        edge_types: set[str] | None = None,
    ) -> list[tuple[str, int, str]]:
        """BFS 从 *start_id* 出发, 返回可达节点.

        Args:
            start_id: 起始节点 ID.
            max_depth: 最大深度.
            edge_types: 限制边类型 (``None`` 表示所有).

        Returns:
            ``[(node_id, depth, edge_type), ...]`` 列表.
        """
        visited: set[str] = {start_id}
        result: list[tuple[str, int, str]] = []
        queue: deque[tuple[str, int, str]] = deque(
            [(start_id, 0, "self")]
        )

        while queue:
            node_id, depth, via_type = queue.popleft()
            if node_id != start_id:
                result.append((node_id, depth, via_type))
            if depth >= max_depth:
                continue

            for target, etype, _weight in self._adj_out.get(node_id, []):
                if target in visited:
                    continue
                if edge_types and etype not in edge_types:
                    continue
                visited.add(target)
                queue.append((target, depth + 1, etype))

        return result

    def dfs(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        edge_types: set[str] | None = None,
    ) -> list[tuple[str, int, str]]:
        """DFS 从 *start_id* 出发, 返回可达节点.

        Args:
            start_id: 起始节点 ID.
            max_depth: 最大深度.
            edge_types: 限制边类型.

        Returns:
            ``[(node_id, depth, edge_type), ...]`` 列表.
        """
        visited: set[str] = {start_id}
        result: list[tuple[str, int, str]] = []

        def _dfs(current: str, depth: int, via: str) -> None:
            if depth > max_depth:
                return
            if current != start_id:
                result.append((current, depth, via))
            for target, etype, _weight in self._adj_out.get(current, []):
                if target in visited:
                    continue
                if edge_types and etype not in edge_types:
                    continue
                visited.add(target)
                _dfs(target, depth + 1, etype)

        _dfs(start_id, 0, "self")
        return result

    # ------------------------------------------------------------------
    # Callers / Callees
    # ------------------------------------------------------------------

    def get_callers(
        self, node_id: str, *, depth: int = 3
    ) -> list[tuple[str, int]]:
        """获取调用 *node_id* 的所有函数 (callers).

        Args:
            node_id: 目标节点 ID.
            depth: 向上追溯深度.

        Returns:
            ``[(caller_id, depth), ...]`` 按深度排序.
        """
        if self._queries is not None:
            rows = self._queries.get_callers(node_id, depth=depth)
            return [(r["id"], r.get("level", 0)) for r in rows]

        # JSON 模式: 反向 BFS
        visited = {node_id}
        result: list[tuple[str, int]] = []
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            node, d = queue.popleft()
            if d >= depth:
                continue
            for source, etype, _w in self._adj_in.get(node, []):
                if etype != "calls":
                    continue
                if source in visited:
                    continue
                visited.add(source)
                result.append((source, d + 1))
                queue.append((source, d + 1))

        return result

    def get_callees(
        self, node_id: str, *, depth: int = 3
    ) -> list[tuple[str, int]]:
        """获取 *node_id* 调用的所有函数 (callees).

        Args:
            node_id: 源节点 ID.
            depth: 向下追溯深度.

        Returns:
            ``[(callee_id, depth), ...]`` 按深度排序.
        """
        if self._queries is not None:
            rows = self._queries.get_callees(node_id, depth=depth)
            return [(r["id"], r.get("level", 0)) for r in rows]

        # JSON 模式: 正向 BFS
        visited = {node_id}
        result: list[tuple[str, int]] = []
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            node, d = queue.popleft()
            if d >= depth:
                continue
            for target, etype, _w in self._adj_out.get(node, []):
                if etype != "calls":
                    continue
                if target in visited:
                    continue
                visited.add(target)
                result.append((target, d + 1))
                queue.append((target, d + 1))

        return result

    # ------------------------------------------------------------------
    # 影响范围分析
    # ------------------------------------------------------------------

    def get_impact(
        self,
        node_id: str,
        *,
        depth: int = 2,
        edge_types: set[str] | None = None,
    ) -> dict[str, list[str]]:
        """分析修改 *node_id* 的影响范围.

        Returns:
            ``{"direct": [...], "indirect": [...]}`` 按距离分组.
        """
        if edge_types is None:
            edge_types = {
                "calls",
                "imports",
                "contains",
                "inherits",
                "implements",
                "references",
            }

        all_reachable = self.bfs(
            node_id, max_depth=depth, edge_types=edge_types
        )

        direct = [
            node for node, d, _ in all_reachable if d == 1
        ]
        indirect = [
            node for node, d, _ in all_reachable if d >= 2
        ]

        return {"direct": direct, "indirect": indirect}

    # ------------------------------------------------------------------
    # 路径查找
    # ------------------------------------------------------------------

    def find_path(
        self,
        from_id: str,
        to_id: str,
        *,
        max_depth: int = 5,
    ) -> list[str] | None:
        """查找 *from_id* 到 *to_id* 的最短路径 (BFS).

        Args:
            from_id: 起始节点 ID.
            to_id: 目标节点 ID.
            max_depth: 最大搜索深度.

        Returns:
            节点 ID 路径列表, 或 ``None`` 表示未找到.
        """
        if from_id == to_id:
            return [from_id]

        visited = {from_id}
        parent: dict[str, str] = {}
        queue: deque[str] = deque([from_id])

        while queue:
            node = queue.popleft()
            for target, _etype, _w in self._adj_out.get(node, []):
                if target in visited:
                    continue
                visited.add(target)
                parent[target] = node
                if target == to_id:
                    # Reconstruct path
                    path = [to_id]
                    current = to_id
                    while current in parent:
                        current = parent[current]
                        path.append(current)
                    return list(reversed(path))
                queue.append(target)
                if len(parent) > 10000:  # safety limit
                    return None

        return None

    # ------------------------------------------------------------------
    # 类型层次
    # ------------------------------------------------------------------

    def get_type_hierarchy(
        self, node_id: str
    ) -> dict[str, list[str]]:
        """获取类型的继承层次.

        Returns:
            ``{"parents": [...], "children": [...]}``.
        """
        parents: list[str] = []
        children: list[str] = []

        for target, etype, _w in self._adj_out.get(node_id, []):
            if etype in ("inherits", "implements"):
                parents.append(target)

        for source, etype, _w in self._adj_in.get(node_id, []):
            if etype in ("inherits", "implements"):
                children.append(source)

        return {"parents": parents, "children": children}
