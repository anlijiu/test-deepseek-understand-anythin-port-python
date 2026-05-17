"""增量 schema 迁移框架 — 基于 ``PRAGMA user_version`` 版本管理.

每次 schema 变更定义为一个独立的迁移步骤, 按版本号顺序执行.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 当前最新 schema 版本
CURRENT_VERSION = 1

# 迁移注册表: version -> migration_function
Migrations = list[tuple[int, str, Callable[[sqlite3.Connection], None]]]


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Version 1: 初始 schema — 节点、边、元数据、FTS5 全文索引."""
    conn.executescript("""
        -- 节点表
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            file_path TEXT,
            line_start INTEGER,
            line_end INTEGER,
            summary TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',          -- JSON array
            complexity TEXT DEFAULT 'simple',
            language_notes TEXT,
            domain_meta TEXT,                -- JSON object
            knowledge_meta TEXT              -- JSON object
        );

        -- 边表
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            type TEXT NOT NULL,
            direction TEXT DEFAULT 'forward',
            description TEXT,
            weight REAL DEFAULT 1.0,
            FOREIGN KEY (source) REFERENCES nodes(id),
            FOREIGN KEY (target) REFERENCES nodes(id)
        );

        -- 边去重索引
        CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique
            ON edges(source, target, type);

        -- 节点类型索引
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
        -- 节点名称索引
        CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
        -- 文件路径索引
        CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
        -- 边类型索引
        CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
        -- 边源节点索引
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        -- 边目标节点索引
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);

        -- 项目元数据
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- 文件指纹
        CREATE TABLE IF NOT EXISTS fingerprints (
            file_path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- FTS5 全文搜索 (节点名称 + 摘要)
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            name, summary, tags,
            content='nodes',
            content_rowid='rowid'
        );
    """)


# ---------------------------------------------------------------------------
# 迁移注册表
# ---------------------------------------------------------------------------

MIGRATIONS: Migrations = [
    (1, "Initial schema: nodes, edges, meta, fingerprints, FTS5", _migrate_v1),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """读取当前 schema 版本.

    Args:
        conn: SQLite 数据库连接.

    Returns:
        当前 ``user_version`` 值 (0 表示未初始化).
    """
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_version(conn: sqlite3.Connection, version: int) -> None:
    """设置 schema 版本.

    Args:
        conn: SQLite 数据库连接.
        version: 新版本号.
    """
    conn.execute(f"PRAGMA user_version = {version}")


def migrate(conn: sqlite3.Connection, target_version: int = CURRENT_VERSION) -> int:
    """执行所有待处理的迁移.

    从当前 ``user_version`` 开始, 按顺序执行每个迁移步骤.
    每次迁移包装在独立的事务中.

    Args:
        conn: SQLite 数据库连接.
        target_version: 目标版本 (默认 ``CURRENT_VERSION``).

    Returns:
        最终版本号.
    """
    current = get_current_version(conn)

    if current >= target_version:
        logger.debug(
            "Schema version %d already at or above target %d",
            current, target_version,
        )
        return current

    for version, description, migrate_fn in MIGRATIONS:
        if version <= current:
            continue
        if version > target_version:
            break

        logger.info("Running migration v%d: %s", version, description)
        try:
            migrate_fn(conn)
            set_version(conn, version)
            conn.commit()
            logger.info("Migration v%d applied successfully", version)
        except Exception:
            conn.rollback()
            logger.exception("Migration v%d failed: %s", version, description)
            raise

    final = get_current_version(conn)
    logger.info("Schema migration complete: v%d → v%d", current, final)
    return final
