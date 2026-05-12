"""Batch-output normalisation — fixes LLM-generated node IDs, complexity, and edges.

Python port of the TypeScript ``normalize-graph.ts``.  This runs **before**
the schema validation pipeline (``sanitize_graph`` / ``auto_fix_graph`` /
``validate_graph``) and handles concerns that pipeline does not cover:
malformed IDs, numeric complexity, edge reference rewriting after ID
correction, and node/edge deduplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ===========================================================================
# Prefix ↔ type mappings
# ===========================================================================

# Valid ID prefixes (must appear as a leading colon-delimited segment)
_VALID_PREFIXES: set[str] = {
    "file",
    "func",
    "class",
    "module",
    "concept",
    "config",
    "document",
    "service",
    "table",
    "endpoint",
    "pipeline",
    "schema",
    "resource",
    "domain",
    "flow",
    "step",
}

# Node type → canonical ID prefix
TYPE_TO_PREFIX: dict[str, str] = {
    "file": "file",
    "function": "func",
    "class": "class",
    "module": "module",
    "concept": "concept",
    "config": "config",
    "document": "document",
    "service": "service",
    "table": "table",
    "endpoint": "endpoint",
    "pipeline": "pipeline",
    "schema": "schema",
    "resource": "resource",
    "domain": "domain",
    "flow": "flow",
    "step": "step",
}

# ID prefix → node type (reverse of TYPE_TO_PREFIX)
_PREFIX_TO_TYPE: dict[str, str] = {
    "file": "file",
    "func": "function",
    "class": "class",
    "module": "module",
    "concept": "concept",
    "config": "config",
    "document": "document",
    "service": "service",
    "table": "table",
    "endpoint": "endpoint",
    "pipeline": "pipeline",
    "schema": "schema",
    "resource": "resource",
    "domain": "domain",
    "flow": "flow",
    "step": "step",
}

# ===========================================================================
# Complexity normalisation
# ===========================================================================

_VALID_COMPLEXITIES: set[str] = {"simple", "moderate", "complex"}

_COMPLEXITY_STRING_MAP: dict[str, str] = {
    "low": "simple",
    "easy": "simple",
    "trivial": "simple",
    "basic": "simple",
    "medium": "moderate",
    "intermediate": "moderate",
    "mid": "moderate",
    "average": "moderate",
    "high": "complex",
    "hard": "complex",
    "difficult": "complex",
    "advanced": "complex",
}

# ===========================================================================
# Data structures
# ===========================================================================


@dataclass
class DroppedEdge:
    """Record of a dangling edge that was removed during normalisation."""

    source: str
    target: str
    type: str
    reason: str  # "missing-source" | "missing-target" | "missing-both"


@dataclass
class NormalizationStats:
    """Statistics gathered during batch normalisation."""

    ids_fixed: int = 0
    complexity_fixed: int = 0
    edges_rewritten: int = 0
    dangling_edges_dropped: int = 0
    dropped_edges: list[dict[str, str]] = field(default_factory=list)


@dataclass
class NormalizeBatchResult:
    """Result of :func:`normalize_batch_output`."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    id_map: dict[str, str]
    stats: NormalizationStats


# ===========================================================================
# Internal helpers
# ===========================================================================


def _strip_to_valid_prefix(node_id: str) -> tuple[str | None, str]:
    """Strip non-valid colon-separated prefixes, returning the first valid
    prefix found and the remaining path.

    Args:
        node_id: A possibly malformed node ID.

    Returns:
        A ``(prefix, path)`` tuple.  *prefix* is ``None`` when no valid
        prefix was found.
    """
    remaining = node_id

    while True:
        colon_idx = remaining.find(":")
        if colon_idx <= 0:
            break

        segment = remaining[:colon_idx]
        if segment in _VALID_PREFIXES:
            # Check for double valid prefix (e.g. "file:file:src/foo.ts")
            rest = remaining[colon_idx + 1 :]
            inner_colon_idx = rest.find(":")
            if (
                inner_colon_idx > 0
                and rest[:inner_colon_idx] in _VALID_PREFIXES
            ):
                # Double-prefixed — skip the outer, recurse on inner
                remaining = rest
                continue
            return segment, rest

        # Not a valid prefix — strip it and continue
        remaining = remaining[colon_idx + 1 :]

    return None, remaining


def _infer_type_from_id(node_id: str) -> str:
    """Infer node type from an ID's prefix (e.g. ``"step:foo"`` → ``"step"``).

    Falls back to ``"file"``.
    """
    colon_idx = node_id.find(":")
    if colon_idx > 0:
        prefix = node_id[:colon_idx]
        if prefix in _PREFIX_TO_TYPE:
            return _PREFIX_TO_TYPE[prefix]
    return "file"


# ===========================================================================
# Public API
# ===========================================================================


def normalize_node_id(
    node_id: str,
    node: dict[str, Any],
) -> str:
    """Normalize a node ID to the canonical ``type:path`` format.

    Handles double-prefixed IDs, project-name-prefixed IDs, bare paths,
    and reconstruction for function/class/step nodes.  Idempotent —
    already-correct IDs pass through unchanged.

    Args:
        node_id: The raw node ID (may be malformed).
        node: A dict with keys ``type``, and optionally ``filePath``,
            ``name``, and ``parentFlowSlug``.

    Returns:
        The canonical node ID string.
    """
    trimmed = node_id.strip()
    if not trimmed:
        return trimmed

    node_type = str(node.get("type", "file"))
    expected_prefix = TYPE_TO_PREFIX.get(node_type)
    prefix, path = _strip_to_valid_prefix(trimmed)

    if prefix is not None:
        # For step nodes with filePath, reconstruct with flow discriminator
        if node_type == "step" and node.get("filePath"):
            segments = path.split(":")
            step_slug = segments[-1] if segments else path
            flow_slug = segments[-2] if len(segments) > 1 else ""
            if flow_slug:
                return f"{prefix}:{flow_slug}:{node['filePath']}:{step_slug}"
            return f"{prefix}:{node['filePath']}:{step_slug}"
        return f"{prefix}:{path}"

    # No valid prefix found — bare path
    if expected_prefix is not None:
        # For func/class, reconstruct from filePath + name if available
        if node_type in ("function", "class") and node.get(
            "filePath"
        ) and node.get("name"):
            return (
                f"{expected_prefix}:{node['filePath']}:{node['name']}"
            )
        # For step nodes with filePath
        if node_type == "step" and node.get("filePath"):
            slug = path.lower().replace(" ", "-")
            parent_flow = node.get("parentFlowSlug")
            if parent_flow:
                return (
                    f"{expected_prefix}:{parent_flow}"
                    f":{node['filePath']}:{slug}"
                )
            return f"{expected_prefix}:{node['filePath']}:{slug}"
        return f"{expected_prefix}:{path}"

    return trimmed


def normalize_complexity(value: Any) -> str:
    """Normalize a complexity value to ``"simple"`` | ``"moderate"`` | ``"complex"``.

    Handles both string aliases and numeric scales.  Unknown values
    default to ``"moderate"``.

    Args:
        value: A string alias, numeric level, or any other value.

    Returns:
        One of the three canonical complexity strings.
    """
    if isinstance(value, str):
        lower = value.lower().strip()
        if lower in _VALID_COMPLEXITIES:
            return lower
        aliased = _COMPLEXITY_STRING_MAP.get(lower)
        if aliased is not None:
            return aliased
        return "moderate"

    if isinstance(value, (int, float)) and value == value and value >= 1:
        # Finite number >= 1
        if value <= 3:
            return "simple"
        if value <= 6:
            return "moderate"
        return "complex"

    return "moderate"


def normalize_batch_output(
    data: dict[str, Any],
) -> NormalizeBatchResult:
    """Normalize a merged batch of nodes and edges from LLM output.

    Performs two passes:

    1. **Normalize node IDs** — fix malformed IDs (double prefixes,
       project-name prefixes, bare paths) and numeric complexity values.
    2. **Rewrite & deduplicate edges** — update edge references to point
       to normalized node IDs, drop dangling edges, and deduplicate by
       ``source|target|type`` key.

    This runs **before** the schema validation pipeline.

    Args:
        data: A dict with ``"nodes"`` and ``"edges"`` lists of raw dicts.

    Returns:
        A ``NormalizeBatchResult`` with normalized nodes, edges, an ID
        mapping, and statistics.
    """
    stats = NormalizationStats()
    id_map: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Build step→flow slug map from flow_step edges
    # ------------------------------------------------------------------
    step_to_flow_slug: dict[str, str] = {}
    flow_node_names: dict[str, str] = {}
    for raw in data.get("nodes", []):
        if str(raw.get("type", "")) == "flow" and raw.get("id") and raw.get(
            "name"
        ):
            flow_node_names[str(raw["id"])] = (
                str(raw["name"]).lower().replace(" ", "-")
            )
    for raw in data.get("edges", []):
        if (
            str(raw.get("type", "")) == "flow_step"
            and raw.get("source")
            and raw.get("target")
        ):
            flow_slug = flow_node_names.get(str(raw["source"]))
            if flow_slug:
                step_to_flow_slug[str(raw["target"])] = flow_slug

    # ------------------------------------------------------------------
    # Pass 1: Normalize node IDs and numeric complexity
    # ------------------------------------------------------------------
    nodes: list[dict[str, Any]] = []
    for raw in data.get("nodes", []):
        old_id = str(raw.get("id", ""))
        node_type = str(raw.get("type", "file"))
        new_id = normalize_node_id(
            old_id,
            {
                "type": node_type,
                "filePath": raw.get("filePath")
                if isinstance(raw.get("filePath"), str)
                else None,
                "name": raw.get("name")
                if isinstance(raw.get("name"), str)
                else None,
                "parentFlowSlug": step_to_flow_slug.get(old_id)
                if node_type == "step"
                else None,
            },
        )

        if new_id != old_id:
            stats.ids_fixed += 1
        id_map[old_id] = new_id

        result: dict[str, Any] = {**raw, "id": new_id}

        # Normalize both numeric and non-canonical string complexity values
        if "complexity" in raw:
            normalized = normalize_complexity(raw["complexity"])
            if normalized != raw["complexity"]:
                result["complexity"] = normalized
                stats.complexity_fixed += 1

        nodes.append(result)

    # Deduplicate nodes (keep last occurrence)
    seen_ids: dict[str, int] = {}
    for i, node in enumerate(nodes):
        seen_ids[str(node["id"])] = i
    deduped_nodes = [
        n for i, n in enumerate(nodes) if seen_ids[str(n["id"])] == i
    ]
    valid_node_ids: set[str] = {str(n["id"]) for n in deduped_nodes}

    # ------------------------------------------------------------------
    # Pass 2: Rewrite edge references and deduplicate
    # ------------------------------------------------------------------
    edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    for raw in data.get("edges", []):
        old_source = str(raw.get("source", ""))
        old_target = str(raw.get("target", ""))
        new_source = id_map.get(old_source, old_source)
        new_target = id_map.get(old_target, old_target)

        # Fallback: if endpoint not found in id_map, normalize it directly
        if new_source not in valid_node_ids:
            inferred_type = _infer_type_from_id(new_source)
            normalized = normalize_node_id(
                new_source, {"type": inferred_type}
            )
            if normalized in valid_node_ids:
                new_source = normalized
        if new_target not in valid_node_ids:
            inferred_type = _infer_type_from_id(new_target)
            normalized = normalize_node_id(
                new_target, {"type": inferred_type}
            )
            if normalized in valid_node_ids:
                new_target = normalized

        if new_source != old_source or new_target != old_target:
            stats.edges_rewritten += 1

        # Drop dangling edges
        if new_source not in valid_node_ids or new_target not in valid_node_ids:
            missing_source = new_source not in valid_node_ids
            missing_target = new_target not in valid_node_ids
            stats.dangling_edges_dropped += 1
            if missing_source and missing_target:
                reason = "missing-both"
            elif missing_source:
                reason = "missing-source"
            else:
                reason = "missing-target"
            stats.dropped_edges.append(
                {
                    "source": new_source,
                    "target": new_target,
                    "type": str(raw.get("type", "")),
                    "reason": reason,
                }
            )
            continue

        # Deduplicate by composite key (source + target + type)
        edge_type = str(raw.get("type", ""))
        edge_key = f"{new_source}|{new_target}|{edge_type}"
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append({**raw, "source": new_source, "target": new_target})

    return NormalizeBatchResult(
        nodes=deduped_nodes,
        edges=edges,
        id_map=id_map,
        stats=stats,
    )
