"""Persistence layer — save/load graph, meta, fingerprints, and config.

Python port of persistence/index.ts.  Uses pathlib.Path for all file I/O
instead of Node's fs/path.

提供两种后端:
  - ``"json"`` (默认): JSON 文件持久化 (向后兼容)
  - ``"sqlite"``: SQLite + FTS5 全文搜索
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from understand_anything.schema import validate_graph
from understand_anything.types import AnalysisMeta, KnowledgeGraph, ProjectConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = ".understand-anything"
GRAPH_FILE = "knowledge-graph.json"
META_FILE = "meta.json"
FINGERPRINTS_FILE = "fingerprints.json"
CONFIG_FILE = "config.json"

# Legacy filenames for backward-compatible reading.
_LEGACY_META_FILE = "analysis-meta.json"
_LEGACY_CONFIG_FILE = "project-config.json"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def output_dir(project_root: Path) -> Path:
    """Return the ``.understand-anything`` directory path (does not create)."""
    return project_root / DEFAULT_OUTPUT_DIR


def _ensure_output_dir(project_root: Path) -> Path:
    """Create the output directory if it does not exist and return it."""
    d = output_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    return d


def graph_path(project_root: Path) -> Path:
    """Path to the knowledge graph JSON file."""
    return output_dir(project_root) / GRAPH_FILE


def meta_path(project_root: Path) -> Path:
    """Path to the analysis metadata JSON file."""
    return output_dir(project_root) / META_FILE


def fingerprints_path(project_root: Path) -> Path:
    """Path to the fingerprints JSON file."""
    return output_dir(project_root) / FINGERPRINTS_FILE


def config_path(project_root: Path) -> Path:
    """Path to the project config JSON file."""
    return output_dir(project_root) / CONFIG_FILE


# ---------------------------------------------------------------------------
# Knowledge graph persistence
# ---------------------------------------------------------------------------


def _sanitize_graph_file_paths(
    graph: KnowledgeGraph, project_root: Path
) -> KnowledgeGraph:
    """Return a copy of *graph* with all ``filePath`` values sanitised.

    Rules (matching TS ``saveGraph`` behaviour):

    - Absolute paths inside *project_root* → relative to *project_root*
    - Absolute paths outside *project_root* → basename only
    - Relative paths → kept as-is
    - ``None`` → kept as ``None``

    The original *graph* is never mutated.
    """
    resolved_root = project_root.resolve()
    graph_copy = graph.model_copy(deep=True)

    for node in graph_copy.nodes:
        fp = node.file_path
        if fp is None:
            continue
        path = Path(fp)
        if path.is_absolute():
            try:
                path.relative_to(resolved_root)
            except ValueError:
                # Outside project — keep basename only.
                node.file_path = path.name
            else:
                # Inside project — make relative.
                node.file_path = str(path.relative_to(resolved_root))

    return graph_copy


def save_graph(project_root: Path, graph: KnowledgeGraph) -> Path:
    """Serialize *graph* to JSON and write to the output directory.

    Returns the path to the written file.

    File paths are sanitised before writing so the persisted JSON never
    leaks absolute paths (see :func:`_sanitize_graph_file_paths`).
    """
    d = _ensure_output_dir(project_root)
    fp = d / GRAPH_FILE
    sanitized = _sanitize_graph_file_paths(graph, project_root)
    fp.write_text(sanitized.model_dump_json(indent=2, by_alias=True))
    return fp


def load_graph(
    project_root: Path, *, validate: bool = True
) -> KnowledgeGraph | None:
    """Load a knowledge graph from the output directory.

    Args:
        project_root: Project root directory.
        validate: If ``True`` (default), run the project validation pipeline
            from :func:`understand_anything.schema.validate_graph`; validation
            failures return ``None``. If ``False``, only parse the JSON into a
            :class:`KnowledgeGraph` with Pydantic model validation.

    Returns:
        ``None`` if the file does not exist or cannot be parsed.
    """
    fp = graph_path(project_root)
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text())
        if validate:
            result = validate_graph(data)
            if not result.success or result.data is None:
                return None
            data = result.data
        return KnowledgeGraph.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Analysis metadata persistence
# ---------------------------------------------------------------------------


def save_meta(project_root: Path, meta: AnalysisMeta) -> Path:
    """Persist analysis metadata as JSON."""
    d = _ensure_output_dir(project_root)
    fp = d / META_FILE
    fp.write_text(meta.model_dump_json(indent=2, by_alias=True))
    return fp


def load_meta(project_root: Path) -> AnalysisMeta | None:
    """Load analysis metadata.  Returns ``None`` if missing or corrupt.

    Tries the contract filename first (``meta.json``), then the legacy
    Python filename (``analysis-meta.json``) for backward compatibility.
    """
    out = output_dir(project_root)
    fp = out / META_FILE
    legacy_fp = out / _LEGACY_META_FILE

    # Prefer contract filename; fall back to legacy.
    if not fp.is_file() and legacy_fp.is_file():
        fp = legacy_fp

    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text())
        return AnalysisMeta.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None


def touch_meta(
    project_root: Path,
    *,
    git_commit_hash: str,
    version: str = "1.0.0",
    analyzed_files: int = 0,
) -> AnalysisMeta:
    """Create or update analysis metadata with the current timestamp.

    Returns the new ``AnalysisMeta`` (also written to disk).
    """
    meta = AnalysisMeta(
        lastAnalyzedAt=datetime.now(timezone.utc).isoformat(),
        gitCommitHash=git_commit_hash,
        version=version,
        analyzedFiles=analyzed_files,
    )
    save_meta(project_root, meta)
    return meta


# ---------------------------------------------------------------------------
# Fingerprint persistence
# ---------------------------------------------------------------------------


def save_fingerprints(
    project_root: Path, fingerprints: dict[str, str]
) -> Path:
    """Persist file-path → SHA-256 hex digest mapping as JSON."""
    d = _ensure_output_dir(project_root)
    fp = d / FINGERPRINTS_FILE
    fp.write_text(json.dumps(fingerprints, indent=2))
    return fp


def load_fingerprints(project_root: Path) -> dict[str, str]:
    """Load the fingerprints mapping.  Returns an empty dict on any error."""
    fp = fingerprints_path(project_root)
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text())
    except json.JSONDecodeError:
        return {}
    else:
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}


# ---------------------------------------------------------------------------
# Project config persistence
# ---------------------------------------------------------------------------


def save_config(project_root: Path, config: ProjectConfig) -> Path:
    """Persist project configuration (e.g. auto-update opt-in)."""
    d = _ensure_output_dir(project_root)
    fp = d / CONFIG_FILE
    fp.write_text(config.model_dump_json(indent=2, by_alias=True))
    return fp


def load_config(project_root: Path) -> ProjectConfig:
    """Load project config.  Returns defaults if file is missing or corrupt.

    Tries the contract filename first (``config.json``), then the legacy
    Python filename (``project-config.json``) for backward compatibility.
    """
    out = output_dir(project_root)
    fp = out / CONFIG_FILE
    legacy_fp = out / _LEGACY_CONFIG_FILE

    if not fp.is_file() and legacy_fp.is_file():
        fp = legacy_fp

    if not fp.is_file():
        return ProjectConfig(autoUpdate=False)
    try:
        data = json.loads(fp.read_text())
        return ProjectConfig.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return ProjectConfig(autoUpdate=False)


# ---------------------------------------------------------------------------
# Bulk helpers
# ---------------------------------------------------------------------------


def clear_all(project_root: Path) -> None:
    """Remove all persisted files from the output directory.

    The directory itself is left in place.  Does nothing if the directory
    does not exist.
    """
    d = output_dir(project_root)
    if not d.is_dir():
        return
    for child in d.iterdir():
        if child.is_file():
            child.unlink()


def load_all(
    project_root: Path,
) -> dict[str, Any]:
    """Load graph, meta, fingerprints, and config in a single call.

    Returns a dict with keys ``graph``, ``meta``, ``fingerprints``,
    ``config``.  Any entry that cannot be loaded will be ``None`` (or
    ``{}`` for fingerprints, default config for config).
    """
    return {
        "graph": load_graph(project_root),
        "meta": load_meta(project_root),
        "fingerprints": load_fingerprints(project_root),
        "config": load_config(project_root),
    }


# ---------------------------------------------------------------------------
# 后端选择工厂 (v2: 保持 JSON 和 SQLite 独立, 不强行包装)
# ---------------------------------------------------------------------------


def create_backend(
    project_root: str | Path,
    *,
    backend: Literal["json", "sqlite"] = "json",
) -> tuple[Literal["json", "sqlite"], Any]:
    """创建持久化后端.

    v2 设计: JSON 后端使用模块级函数 (save_graph 等), SQLite 后端返回
    ``SqliteBackend`` 实例. 两者保持独立, 调用方自行选择.

    Args:
        project_root: 项目根目录.
        backend: 后端类型.

    Returns:
        ``(backend_type, sqlite_instance_or_none)`` 元组.
        当 ``backend="json"`` 时 sqlite 为 ``None``.
    """
    if backend == "sqlite":
        from understand_anything.persistence.sqlite_backend import (
            SqliteBackend,
        )

        return ("sqlite", SqliteBackend(Path(project_root)))
    return ("json", None)

