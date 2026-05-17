"""SQLite 持久化后端 — WAL 模式 + FTS5 全文搜索 + 增量迁移.

提供 ``SqliteBackend`` 类, 管理数据库连接生命周期、节点/边的
批量写入、以及通过 ``QueryBuilder`` 执行图查询.

特点:
  - WAL (Write-Ahead Logging) 模式, 支持高并发读写
  - FTS5 全文索引, 支持中文和英文关键词搜索
  - 基于 ``PRAGMA user_version`` 的增量 schema 迁移
  - 标准库 ``sqlite3`` 实现, 无外部 ORM 依赖
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import Self

from understand_anything.persistence.migrations import CURRENT_VERSION, migrate
from understand_anything.persistence.queries import QueryBuilder

if TYPE_CHECKING:
    from understand_anything.types import (
        AnalysisMeta,
        GraphEdge,
        GraphNode,
        KnowledgeGraph,
    )

logger = logging.getLogger(__name__)

# 数据库默认文件名
DEFAULT_DB_NAME = "graph.db"


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------


def _node_to_dict(node: GraphNode) -> dict:
    """将 GraphNode 序列化为 SQLite 行字典."""
    return {
        "id": node.id,
        "type": node.type.value,
        "name": node.name,
        "file_path": node.file_path,
        "line_start": node.line_range[0] if node.line_range else None,
        "line_end": node.line_range[1] if node.line_range else None,
        "summary": node.summary,
        "tags": node.tags,
        "complexity": node.complexity,
        "language_notes": node.language_notes,
        "domain_meta": (
            node.domain_meta.model_dump(by_alias=True)
            if node.domain_meta
            else None
        ),
        "knowledge_meta": (
            node.knowledge_meta.model_dump(by_alias=True)
            if node.knowledge_meta
            else None
        ),
    }


def _edge_to_dict(edge: GraphEdge) -> dict:
    """将 GraphEdge 序列化为 SQLite 行字典."""
    return {
        "source": edge.source,
        "target": edge.target,
        "type": edge.type.value,
        "direction": edge.direction,
        "description": edge.description,
        "weight": edge.weight,
    }


class SqliteBackend:
    """SQLite 持久化适配器.

    管理数据库连接、schema 迁移、图数据读写和全文搜索.

    Example::

        backend = SqliteBackend("/path/to/project")
        backend.save_graph(graph)
        nodes = backend.queries.get_nodes_by_type("function")
        results = backend.queries.search_fts("login")
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        db_name: str = DEFAULT_DB_NAME,
        read_only: bool = False,
    ) -> None:
        """初始化 SQLite 后端.

        Args:
            project_root: 项目根目录 (数据库文件存放在其下 ``.understand-anything/``).
            db_name: 数据库文件名 (默认 ``graph.db``).
            read_only: 只读模式 (跳过迁移和 FTS 触发器创建).
        """
        project_root = Path(project_root)
        db_dir = project_root / ".understand-anything"
        db_dir.mkdir(parents=True, exist_ok=True)

        self._db_path = db_dir / db_name
        self._read_only = read_only

        # 打开连接
        uri = f"file:{self._db_path}?mode=ro" if read_only else str(self._db_path)
        self._conn = sqlite3.connect(
            uri if read_only else str(self._db_path),
            uri=bool(not read_only),  # Use URI only for ro
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # 查询构建器
        self.queries = QueryBuilder(self._conn)

        if not read_only:
            self._init_schema()

    # ------------------------------------------------------------------
    # Schema 初始化
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """执行 schema 迁移并设置 FTS 触发器."""
        version = migrate(self._conn, target_version=CURRENT_VERSION)
        logger.info(
            "SQLite schema initialized at version %d for %s",
            version, self._db_path,
        )

        # FTS5 触发器: 节点插入/更新/删除时自动同步
        self._create_fts_triggers()

    def _create_fts_triggers(self) -> None:
        """创建 FTS5 同步触发器 (如果 FTS5 可用)."""
        try:
            # 检查 FTS5 表是否存在
            self._conn.execute("SELECT 1 FROM nodes_fts LIMIT 0")
        except sqlite3.OperationalError:
            logger.warning("FTS5 not available, skipping trigger creation")
            return

        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
                INSERT INTO nodes_fts(rowid, name, summary, tags)
                VALUES (new.rowid, new.name, new.summary, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, name, summary, tags)
                VALUES ('delete', old.rowid, old.name, old.summary, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, name, summary, tags)
                VALUES ('delete', old.rowid, old.name, old.summary, old.tags);
                INSERT INTO nodes_fts(rowid, name, summary, tags)
                VALUES (new.rowid, new.name, new.summary, new.tags);
            END;
        """)

    # ------------------------------------------------------------------
    # 图读写
    # ------------------------------------------------------------------

    def save_graph(self, graph: KnowledgeGraph) -> int:
        """将完整知识图谱保存到 SQLite.

        ``with self._conn:`` 统一管理事务, 保证 DELETE + INSERT + meta
        全部原子性执行, 避免嵌套事务错误.

        Args:
            graph: 知识图谱 Pydantic 模型.

        Returns:
            写入的节点总数.
        """
        # 序列化节点和边
        node_dicts = [_node_to_dict(n) for n in graph.nodes]
        edge_dicts = [_edge_to_dict(e) for e in graph.edges]

        with self._conn:
            # 清空旧数据
            self._conn.execute("DELETE FROM edges")
            self._conn.execute("DELETE FROM nodes")
            self._conn.execute("DELETE FROM meta")

            # 批量写入
            self.queries.insert_nodes_batch(node_dicts)
            self.queries.insert_edges_batch(edge_dicts)

            # 保存项目元数据
            self.queries.set_meta("project_name", graph.project.name)
            self.queries.set_meta(
                "project_languages", json.dumps(graph.project.languages)
            )
            self.queries.set_meta(
                "project_frameworks", json.dumps(graph.project.frameworks)
            )
            self.queries.set_meta("analyzed_at", graph.project.analyzed_at)
            self.queries.set_meta(
                "git_commit_hash", graph.project.git_commit_hash
            )
            self.queries.set_meta("graph_version", graph.version)

        logger.info(
            "Saved %d nodes and %d edges to %s",
            len(node_dicts), len(edge_dicts), self._db_path,
        )
        return len(node_dicts)

    def save_meta(self, meta: AnalysisMeta) -> None:
        """保存分析元数据.

        Args:
            meta: 分析元数据 Pydantic 模型.
        """
        self.queries.set_meta("last_analyzed_at", meta.last_analyzed_at)
        self.queries.set_meta("git_commit_hash", meta.git_commit_hash)
        self.queries.set_meta("version", meta.version)
        self.queries.set_meta("analyzed_files", str(meta.analyzed_files))
        if meta.theme:
            self.queries.set_meta(
                "theme", json.dumps(meta.theme.model_dump(by_alias=True))
            )
        self._conn.commit()

    def save_fingerprints(
        self, fingerprints: dict[str, str]
    ) -> None:
        """批量保存文件指纹.

        Args:
            fingerprints: ``{file_path: sha256_hex}`` 映射.
        """
        now = datetime.now(timezone.utc).isoformat()
        for file_path, sha256 in fingerprints.items():
            self.queries.set_fingerprint(file_path, sha256, now)
        self._conn.commit()
        logger.info("Saved %d fingerprints", len(fingerprints))

    def load_fingerprints(self) -> dict[str, str]:
        """加载所有文件指纹.

        Returns:
            ``{file_path: sha256_hex}`` 映射.
        """
        rows = self._conn.execute(
            "SELECT file_path, sha256 FROM fingerprints"
        ).fetchall()
        return {r["file_path"]: r["sha256"] for r in rows}

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭数据库连接."""
        with contextlib.suppress(sqlite3.ProgrammingError):
            self._conn.close()
        logger.debug("SQLite connection closed")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def db_path(self) -> Path:
        """数据库文件路径."""
        return self._db_path
