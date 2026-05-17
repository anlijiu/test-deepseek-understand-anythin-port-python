"""预编译 SQL 查询构建器 — 提供约 20 个常用查询."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class QueryBuilder:
    """预编译 SQL 查询集合.

    封装常用图查询操作, 避免在调用方手写 SQL.
    所有查询使用参数化方式, 防止 SQL 注入.

    Example::

        qb = QueryBuilder(conn)
        nodes = qb.get_nodes_by_type("function")
        edges = qb.get_edges_between("source_id", "target_id")
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """使用给定连接初始化查询构建器.

        Args:
            conn: 已打开的 SQLite 连接.
        """
        self._conn = conn

    # ------------------------------------------------------------------
    # 节点查询
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """按 ID 获取单个节点."""
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_nodes_by_type(
        self, node_type: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """按类型获取节点列表."""
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE type = ? LIMIT ?",
            (node_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nodes_by_file(
        self, file_path: str
    ) -> list[dict[str, Any]]:
        """获取指定文件中的所有节点."""
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE file_path = ?", (file_path,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nodes_by_name(
        self, name: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """按名称获取节点 (模糊匹配)."""
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE name LIKE ? LIMIT ?",
            (f"%{name}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_nodes(self) -> int:
        """获取节点总数."""
        row = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return row[0] if row else 0

    def count_nodes_by_type(self) -> dict[str, int]:
        """按类型统计节点数量."""
        rows = self._conn.execute(
            "SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type"
        ).fetchall()
        return {r["type"]: r["cnt"] for r in rows}

    # ------------------------------------------------------------------
    # 边查询
    # ------------------------------------------------------------------

    def get_edge(self, edge_id: int) -> dict[str, Any] | None:
        """按 ID 获取单条边."""
        row = self._conn.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_edges_by_type(
        self, edge_type: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """按类型获取边列表."""
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE type = ? LIMIT ?",
            (edge_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges_by_source(
        self, source_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """获取从指定节点出发的所有边."""
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE source = ? LIMIT ?",
            (source_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges_by_target(
        self, target_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """获取指向指定节点的所有边."""
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE target = ? LIMIT ?",
            (target_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges_between(
        self, source_id: str, target_id: str
    ) -> list[dict[str, Any]]:
        """获取两个节点之间的所有边."""
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE source = ? AND target = ?",
            (source_id, target_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_edges(self) -> int:
        """获取边总数."""
        row = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # 图遍历查询
    # ------------------------------------------------------------------

    def get_callers(
        self, node_id: str, *, depth: int = 1
    ) -> list[dict[str, Any]]:
        """获取调用指定节点的所有函数 (callers).

        递归 CTE 实现, 支持指定深度.
        """
        rows = self._conn.execute(
            """
            WITH RECURSIVE callers AS (
                SELECT e.source, e.target, e.type, 0 as level
                FROM edges e
                WHERE e.target = ? AND e.type = 'calls'
                UNION ALL
                SELECT e.source, e.target, e.type, c.level + 1
                FROM edges e
                JOIN callers c ON e.target = c.source
                WHERE e.type = 'calls' AND c.level < ?
            )
            SELECT DISTINCT n.*, c.level
            FROM callers c
            JOIN nodes n ON n.id = c.source
            ORDER BY c.level
            """,
            (node_id, depth - 1),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_callees(
        self, node_id: str, *, depth: int = 1
    ) -> list[dict[str, Any]]:
        """获取指定节点调用的所有函数 (callees)."""
        rows = self._conn.execute(
            """
            WITH RECURSIVE callees AS (
                SELECT e.source, e.target, e.type, 0 as level
                FROM edges e
                WHERE e.source = ? AND e.type = 'calls'
                UNION ALL
                SELECT e.source, e.target, e.type, c.level + 1
                FROM edges e
                JOIN callees c ON e.source = c.target
                WHERE e.type = 'calls' AND c.level < ?
            )
            SELECT DISTINCT n.*, c.level
            FROM callees c
            JOIN nodes n ON n.id = c.target
            ORDER BY c.level
            """,
            (node_id, depth - 1),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_children(
        self, node_id: str
    ) -> list[dict[str, Any]]:
        """获取指定节点的直接子节点 (通过 contains 边)."""
        rows = self._conn.execute(
            """
            SELECT n.*
            FROM edges e
            JOIN nodes n ON n.id = e.target
            WHERE e.source = ? AND e.type = 'contains'
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_parent(
        self, node_id: str
    ) -> dict[str, Any] | None:
        """获取指定节点的直接父节点 (通过 contains 边)."""
        row = self._conn.execute(
            """
            SELECT n.*
            FROM edges e
            JOIN nodes n ON n.id = e.source
            WHERE e.target = ? AND e.type = 'contains'
            LIMIT 1
            """,
            (node_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_imports(
        self, node_id: str
    ) -> list[dict[str, Any]]:
        """获取指定文件导入的模块."""
        rows = self._conn.execute(
            """
            SELECT n.*
            FROM edges e
            JOIN nodes n ON n.id = e.target
            WHERE e.source = ? AND e.type = 'imports'
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_exports(
        self, node_id: str
    ) -> list[dict[str, Any]]:
        """获取指定文件的导出符号."""
        rows = self._conn.execute(
            """
            SELECT n.*
            FROM edges e
            JOIN nodes n ON n.id = e.target
            WHERE e.source = ? AND e.type = 'exports'
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # FTS5 全文搜索
    # ------------------------------------------------------------------

    def search_fts(
        self, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """FTS5 全文搜索节点名称和摘要.

        FTS5 不可用时回退到 LIKE 搜索.

        Args:
            query: 搜索关键词.
            limit: 返回结果数上限.

        Returns:
            匹配的节点列表 (按相关度排序).
        """
        try:
            rows = self._conn.execute(
                """
                SELECT n.*
                FROM nodes_fts f
                JOIN nodes n ON n.rowid = f.rowid
                WHERE nodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass  # FTS5 not available, fall through

        # Fallback: LIKE search
        like_query = f"%{query}%"
        rows = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE name LIKE ? OR summary LIKE ? OR tags LIKE ?
            LIMIT ?
            """,
            (like_query, like_query, like_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 元数据查询
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        """获取元数据值."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """设置元数据键值."""
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def get_fingerprint(self, file_path: str) -> str | None:
        """获取文件 SHA-256 指纹."""
        row = self._conn.execute(
            "SELECT sha256 FROM fingerprints WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        return row["sha256"] if row else None

    def set_fingerprint(
        self, file_path: str, sha256: str, updated_at: str
    ) -> None:
        """设置文件指纹."""
        self._conn.execute(
            "INSERT OR REPLACE INTO fingerprints (file_path, sha256, updated_at) "
            "VALUES (?, ?, ?)",
            (file_path, sha256, updated_at),
        )

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def insert_node(self, node: dict[str, Any]) -> None:
        """插入单个节点."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO nodes
            (id, type, name, file_path, line_start, line_end,
             summary, tags, complexity, language_notes, domain_meta, knowledge_meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node["id"],
                node["type"],
                node["name"],
                node.get("file_path"),
                node.get("line_start"),
                node.get("line_end"),
                node.get("summary", ""),
                json.dumps(node.get("tags", [])),
                node.get("complexity", "simple"),
                node.get("language_notes"),
                json.dumps(node["domain_meta"]) if node.get("domain_meta") else None,
                json.dumps(node["knowledge_meta"]) if node.get("knowledge_meta") else None,
            ),
        )

    def insert_edge(self, edge: dict[str, Any]) -> None:
        """插入单条边 (INSERT OR IGNORE 去重)."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO edges
            (source, target, type, direction, description, weight)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                edge["source"],
                edge["target"],
                edge["type"],
                edge.get("direction", "forward"),
                edge.get("description"),
                edge.get("weight", 1.0),
            ),
        )

    def insert_nodes_batch(
        self, nodes: list[dict[str, Any]]
    ) -> int:
        """批量插入节点.

        注意: 不管理事务, 由调用方统一控制.

        Returns:
            实际插入的行数.
        """
        count = 0
        for node in nodes:
            self.insert_node(node)
            count += 1
        return count

    def insert_edges_batch(
        self, edges: list[dict[str, Any]]
    ) -> int:
        """批量插入边.

        注意: 不管理事务, 由调用方统一控制.

        Returns:
            实际插入的行数.
        """
        count = 0
        for edge in edges:
            self.insert_edge(edge)
            count += 1
        return count

    # ------------------------------------------------------------------
    # 统计查询
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """获取图统计信息."""
        return {
            "node_count": self.count_nodes(),
            "edge_count": self.count_edges(),
            "node_types": self.count_nodes_by_type(),
            "schema_version": self._conn.execute(
                "PRAGMA user_version"
            ).fetchone()[0],
        }
