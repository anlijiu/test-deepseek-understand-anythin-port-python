"""Persistence layer — save/load graph, meta, fingerprints, and config.

Python port of persistence/index.ts.  Uses pathlib.Path for all file I/O
instead of Node's fs/path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from understand_anything.types import AnalysisMeta, KnowledgeGraph, ProjectConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = ".understand-anything"
GRAPH_FILE = "knowledge-graph.json"
META_FILE = "analysis-meta.json"
FINGERPRINTS_FILE = "fingerprints.json"
CONFIG_FILE = "project-config.json"


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


def save_graph(project_root: Path, graph: KnowledgeGraph) -> Path:
    """Serialize *graph* to JSON and write to the output directory.

    Returns the path to the written file.
    """
    d = _ensure_output_dir(project_root)
    fp = d / GRAPH_FILE
    fp.write_text(graph.model_dump_json(indent=2, by_alias=False))
    return fp


def load_graph(project_root: Path) -> KnowledgeGraph | None:
    """Load a knowledge graph from the output directory.

    Returns ``None`` if the file does not exist or cannot be parsed.
    """
    fp = graph_path(project_root)
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text())
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
    fp.write_text(meta.model_dump_json(indent=2, by_alias=False))
    return fp


def load_meta(project_root: Path) -> AnalysisMeta | None:
    """Load analysis metadata.  Returns ``None`` if missing or corrupt."""
    fp = meta_path(project_root)
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
    fp.write_text(config.model_dump_json(indent=2, by_alias=False))
    return fp


def load_config(project_root: Path) -> ProjectConfig:
    """Load project config.  Returns defaults if file is missing or corrupt."""
    fp = config_path(project_root)
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
