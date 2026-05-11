"""Validation pipeline — Python port of schema.ts.

Pipeline: sanitize → normalize → auto-fix → validate → referential integrity.

Uses Pydantic v2 for strict schema validation (equivalent to Zod safeParse),
with pre-validation passes that handle LLM-generated noise (aliases, nulls,
missing fields, type coercion).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from understand_anything.types import (
    GraphEdge,
    GraphNode,
    Layer,
    ProjectMeta,
    TourStep,
)

# ===========================================================================
# Alias maps — LLMs commonly generate these instead of canonical values
# ===========================================================================

# Aliases that LLMs commonly generate instead of canonical node types
NODE_TYPE_ALIASES: dict[str, str] = {
    "func": "function",
    "fn": "function",
    "method": "function",
    "interface": "class",
    "struct": "class",
    "mod": "module",
    "pkg": "module",
    "package": "module",
    # Non-code aliases
    "container": "service",
    "deployment": "service",
    "pod": "service",
    "doc": "document",
    "readme": "document",
    "docs": "document",
    "job": "pipeline",
    "ci": "pipeline",
    "route": "endpoint",
    "api": "endpoint",
    "query": "endpoint",
    "mutation": "endpoint",
    "setting": "config",
    "env": "config",
    "configuration": "config",
    "infra": "resource",
    "infrastructure": "resource",
    "terraform": "resource",
    "migration": "table",
    "database": "table",
    "db": "table",
    "view": "table",
    "proto": "schema",
    "protobuf": "schema",
    "definition": "schema",
    "typedef": "schema",
    # Domain aliases — "process" intentionally excluded (ambiguous)
    "business_domain": "domain",
    "business_flow": "flow",
    "business_process": "flow",
    "task": "step",
    "business_step": "step",
    # Knowledge aliases
    "note": "article",
    "page": "article",
    "wiki_page": "article",
    "person": "entity",
    "actor": "entity",
    "organization": "entity",
    "tag": "topic",
    "category": "topic",
    "theme": "topic",
    "assertion": "claim",
    "decision": "claim",
    "thesis": "claim",
    "reference": "source",
    "raw": "source",
    "paper": "source",
}

# Aliases that LLMs commonly generate instead of canonical edge types
EDGE_TYPE_ALIASES: dict[str, str] = {
    "extends": "inherits",
    "invokes": "calls",
    "invoke": "calls",
    "uses": "depends_on",
    "requires": "depends_on",
    "relates_to": "related",
    "related_to": "related",
    "similar": "similar_to",
    "import": "imports",
    "export": "exports",
    "contain": "contains",
    "publish": "publishes",
    "subscribe": "subscribes",
    # Non-code aliases
    "describes": "documents",
    "documented_by": "documents",
    "creates": "provisions",
    "exposes": "serves",
    "listens": "serves",
    "deploys_to": "deploys",
    "migrates_to": "migrates",
    "routes_to": "routes",
    "triggers_on": "triggers",
    "fires": "triggers",
    "defines": "defines_schema",
    # Domain aliases
    "has_flow": "contains_flow",
    "next_step": "flow_step",
    "interacts_with": "cross_domain",
    # Knowledge aliases
    "references": "cites",
    "cites_source": "cites",
    "conflicts_with": "contradicts",
    "disagrees_with": "contradicts",
    "refines": "builds_on",
    "elaborates": "builds_on",
    "illustrates": "exemplifies",
    "instance_of": "exemplifies",
    "example_of": "exemplifies",
    "belongs_to": "categorized_under",
    "tagged_with": "categorized_under",
    "written_by": "authored_by",
    "created_by": "authored_by",
    # Note: "implemented_by" is intentionally NOT aliased to "implements" —
    # it inverts edge direction. The LLM should use "implements" with
    # correct source/target instead.
}

# Aliases for complexity values LLMs commonly generate
COMPLEXITY_ALIASES: dict[str, str] = {
    "low": "simple",
    "easy": "simple",
    "medium": "moderate",
    "intermediate": "moderate",
    "high": "complex",
    "hard": "complex",
    "difficult": "complex",
}

# Aliases for direction values LLMs commonly generate
DIRECTION_ALIASES: dict[str, str] = {
    "to": "forward",
    "outbound": "forward",
    "from": "backward",
    "inbound": "backward",
    "both": "bidirectional",
    "mutual": "bidirectional",
}

# Canonical sets for validation
_CANONICAL_NODE_TYPES: set[str] = {
    "file", "function", "class", "module", "concept",
    "config", "document", "service", "table", "endpoint",
    "pipeline", "schema", "resource",
    "domain", "flow", "step",
    "article", "entity", "topic", "claim", "source",
}

_CANONICAL_EDGE_TYPES: set[str] = {
    "imports", "exports", "contains", "inherits", "implements",
    "calls", "subscribes", "publishes", "middleware",
    "reads_from", "writes_to", "transforms", "validates",
    "depends_on", "tested_by", "configures",
    "related", "similar_to",
    "deploys", "serves", "provisions", "triggers",
    "migrates", "documents", "routes", "defines_schema",
    "contains_flow", "flow_step", "cross_domain",
    "cites", "contradicts", "builds_on", "exemplifies",
    "categorized_under", "authored_by",
}

_CANONICAL_COMPLEXITIES: set[str] = {"simple", "moderate", "complex"}
_CANONICAL_DIRECTIONS: set[str] = {"forward", "backward", "bidirectional"}
_CANONICAL_ENTRY_TYPES: set[str] = {"http", "cli", "event", "cron", "manual"}


# ===========================================================================
# Tier 1: Sanitize — null → undefined, lowercase enum-like strings
# ===========================================================================


def sanitize_graph(data: dict[str, Any]) -> dict[str, Any]:
    """Remove nulls for optional fields, lowercase enum-like strings.

    This operates on a raw dict before any schema validation.  It handles the
    common LLM output patterns: ``null`` for optional fields, mixed-case
    enum values, and missing top-level collections.
    """
    result: dict[str, Any] = dict(data)

    # Null → empty list for top-level collections
    for key in ("tour", "layers"):
        if result.get(key) is None:
            result[key] = []

    # Sanitize nodes
    if isinstance(data.get("nodes"), list):
        sanitized_nodes: list[dict[str, Any]] = []
        for node in data["nodes"]:
            if not isinstance(node, dict):
                sanitized_nodes.append(node)  # type: ignore[arg-type]
                continue
            n: dict[str, Any] = dict(node)
            # Null → delete for optional fields
            for opt_key in ("filePath", "lineRange", "languageNotes"):
                if n.get(opt_key) is None:
                    n.pop(opt_key, None)
            # Lowercase enum-like strings
            if isinstance(n.get("type"), str):
                n["type"] = n["type"].lower()
            if isinstance(n.get("complexity"), str):
                n["complexity"] = n["complexity"].lower()
            sanitized_nodes.append(n)
        result["nodes"] = sanitized_nodes

    # Sanitize edges
    if isinstance(data.get("edges"), list):
        sanitized_edges: list[dict[str, Any]] = []
        for edge in data["edges"]:
            if not isinstance(edge, dict):
                sanitized_edges.append(edge)  # type: ignore[arg-type]
                continue
            e: dict[str, Any] = dict(edge)
            # Null → delete for optional fields
            if e.get("description") is None:
                e.pop("description", None)
            if isinstance(e.get("type"), str):
                e["type"] = e["type"].lower()
            if isinstance(e.get("direction"), str):
                e["direction"] = e["direction"].lower()
            sanitized_edges.append(e)
        result["edges"] = sanitized_edges

    # Sanitize tour steps
    if isinstance(result.get("tour"), list):
        sanitized_tour: list[dict[str, Any]] = []
        for step in result["tour"]:
            if not isinstance(step, dict):
                sanitized_tour.append(step)  # type: ignore[arg-type]
                continue
            s: dict[str, Any] = dict(step)
            if s.get("languageLesson") is None:
                s.pop("languageLesson", None)
            sanitized_tour.append(s)
        result["tour"] = sanitized_tour

    return result


# ===========================================================================
# Alias normalisation — applied after sanitize but before auto-fix
# ===========================================================================


def normalize_graph(data: dict[str, Any]) -> dict[str, Any]:
    """Map LLM-generated type aliases to canonical values.

    Applied to nodes[].type and edges[].type only.  This is separate from
    auto-fix because alias mapping is lossless (same semantics) while
    auto-fix invents defaults.
    """
    result: dict[str, Any] = dict(data)

    if isinstance(data.get("nodes"), list):
        normalized_nodes: list[dict[str, Any]] = []
        for node in data["nodes"]:
            if (
                isinstance(node, dict)
                and isinstance(node.get("type"), str)
                and node["type"] in NODE_TYPE_ALIASES
            ):
                n = dict(node)
                n["type"] = NODE_TYPE_ALIASES[node["type"]]
                normalized_nodes.append(n)
            else:
                normalized_nodes.append(node)  # type: ignore[arg-type]
        result["nodes"] = normalized_nodes

    if isinstance(data.get("edges"), list):
        normalized_edges: list[dict[str, Any]] = []
        for edge in data["edges"]:
            if (
                isinstance(edge, dict)
                and isinstance(edge.get("type"), str)
                and edge["type"] in EDGE_TYPE_ALIASES
            ):
                e = dict(edge)
                e["type"] = EDGE_TYPE_ALIASES[edge["type"]]
                normalized_edges.append(e)
            else:
                normalized_edges.append(edge)  # type: ignore[arg-type]
        result["edges"] = normalized_edges

    return result


# ===========================================================================
# GraphIssue & ValidationResult
# ===========================================================================


class GraphIssue(BaseModel):
    """A single issue discovered during validation."""

    level: Literal["auto-corrected", "dropped", "fatal"]
    category: str
    message: str
    path: str | None = None


class ValidationResult(BaseModel):
    """Full result of the validation pipeline."""

    success: bool
    data: dict[str, Any] | None = None
    errors: list[str] | None = None
    issues: list[GraphIssue] = []
    fatal: str | None = None


# ===========================================================================
# Helpers
# ===========================================================================


def _build_invalid_collection_issue(name: str) -> GraphIssue:
    return GraphIssue(
        level="fatal",
        category="invalid-collection",
        message=f'"{name}" must be an array when present',
        path=name,
    )


def _build_errors(issues: list[GraphIssue], fatal: str | None = None) -> list[str] | None:
    messages = [i.message for i in issues]
    if fatal is not None and fatal not in messages:
        messages.insert(0, fatal)
    return messages or None


# ===========================================================================
# Tier 2: Auto-fix — fill in defaults, coerce types, clamp ranges
# ===========================================================================


def auto_fix_graph(data: dict[str, Any]) -> tuple[dict[str, Any], list[GraphIssue]]:
    """Fill in missing required fields with sensible defaults.

    Returns (fixed_data, issues).  Issues are all ``auto-corrected`` level
    because this tier never drops data or raises fatals.
    """
    issues: list[GraphIssue] = []
    result: dict[str, Any] = dict(data)

    # --- nodes ---
    if isinstance(data.get("nodes"), list):
        fixed_nodes: list[dict[str, Any]] = []
        for i, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                fixed_nodes.append(node)  # type: ignore[arg-type]
                continue
            n: dict[str, Any] = dict(node)
            name: str = str(n.get("name") or n.get("id") or f"index {i}")

            # Missing or empty type → "file"
            if not n.get("type") or not isinstance(n["type"], str):
                n["type"] = "file"
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'nodes[{i}] ("{name}"): missing "type" — defaulted to "file"',
                    path=f"nodes[{i}].type",
                ))

            # Missing or empty complexity → "moderate"
            if not n.get("complexity") or n["complexity"] == "":
                n["complexity"] = "moderate"
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'nodes[{i}] ("{name}"): missing "complexity" — defaulted to "moderate"',
                    path=f"nodes[{i}].complexity",
                ))
            elif isinstance(n["complexity"], str) and n["complexity"] in COMPLEXITY_ALIASES:
                original = n["complexity"]
                n["complexity"] = COMPLEXITY_ALIASES[original]
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="alias",
                    message=f'nodes[{i}] ("{name}"): complexity "{original}" — mapped to "{n["complexity"]}"',
                    path=f"nodes[{i}].complexity",
                ))

            # Missing tags → []
            if not isinstance(n.get("tags"), list):
                n["tags"] = []
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'nodes[{i}] ("{name}"): missing "tags" — defaulted to []',
                    path=f"nodes[{i}].tags",
                ))

            # Missing summary → name
            if not n.get("summary") or not isinstance(n["summary"], str):
                n["summary"] = name
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'nodes[{i}] ("{name}"): missing "summary" — defaulted to name',
                    path=f"nodes[{i}].summary",
                ))

            fixed_nodes.append(n)
        result["nodes"] = fixed_nodes

    # --- edges ---
    if isinstance(data.get("edges"), list):
        fixed_edges: list[dict[str, Any]] = []
        for i, edge in enumerate(data["edges"]):
            if not isinstance(edge, dict):
                fixed_edges.append(edge)  # type: ignore[arg-type]
                continue
            e: dict[str, Any] = dict(edge)

            # Missing type → "depends_on"
            if not e.get("type") or not isinstance(e["type"], str):
                e["type"] = "depends_on"
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'edges[{i}]: missing "type" — defaulted to "depends_on"',
                    path=f"edges[{i}].type",
                ))

            # Missing direction → "forward"
            if not e.get("direction") or not isinstance(e["direction"], str):
                e["direction"] = "forward"
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'edges[{i}]: missing "direction" — defaulted to "forward"',
                    path=f"edges[{i}].direction",
                ))
            elif e["direction"] in DIRECTION_ALIASES:
                original = e["direction"]
                e["direction"] = DIRECTION_ALIASES[original]
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="alias",
                    message=f'edges[{i}]: direction "{original}" — mapped to "{e["direction"]}"',
                    path=f"edges[{i}].direction",
                ))

            # Missing weight → 0.5
            weight = e.get("weight")
            if weight is None:
                e["weight"] = 0.5
                issues.append(GraphIssue(
                    level="auto-corrected",
                    category="missing-field",
                    message=f'edges[{i}]: missing "weight" — defaulted to 0.5',
                    path=f"edges[{i}].weight",
                ))
            elif isinstance(weight, str):
                try:
                    parsed = float(weight)
                    e["weight"] = parsed
                    issues.append(GraphIssue(
                        level="auto-corrected",
                        category="type-coercion",
                        message=f'edges[{i}]: weight was string "{weight}" — coerced to number',
                        path=f"edges[{i}].weight",
                    ))
                except ValueError:
                    e["weight"] = 0.5
                    issues.append(GraphIssue(
                        level="auto-corrected",
                        category="type-coercion",
                        message=f'edges[{i}]: weight "{weight}" is not a valid number — defaulted to 0.5',
                        path=f"edges[{i}].weight",
                    ))

            # Clamp weight to [0, 1]
            if isinstance(e.get("weight"), (int, float)):
                w = float(e["weight"])
                if w < 0 or w > 1:
                    original = w
                    e["weight"] = max(0.0, min(1.0, w))
                    issues.append(GraphIssue(
                        level="auto-corrected",
                        category="out-of-range",
                        message=f'edges[{i}]: weight {original} clamped to {e["weight"]}',
                        path=f"edges[{i}].weight",
                    ))

            fixed_edges.append(e)
        result["edges"] = fixed_edges

    return result, issues


# ===========================================================================
# Pydantic v2 schemas (equivalent to the Zod schemas in TS)
# ===========================================================================


def _validate_with_pydantic(
    model_cls: type[BaseModel], data: dict[str, Any], index: int, label: str
) -> tuple[dict[str, Any] | None, GraphIssue | None]:
    """Try to validate *data* against *model_cls*.

    Returns ``(validated_dict, None)`` on success or ``(None, issue)`` on
    failure.  The ``GraphIssue`` is always ``dropped`` level.
    """
    try:
        validated = model_cls.model_validate(data)
        return validated.model_dump(by_alias=False), None
    except ValidationError as exc:
        first_msg = exc.errors()[0]["msg"] if exc.errors() else "validation failed"
        issue = GraphIssue(
            level="dropped",
            category=f"invalid-{label}",
            message=f"{label}[{index}]: {first_msg} — removed",
            path=f"{label}[{index}]",
        )
        return None, issue


# ===========================================================================
# Full validation pipeline
# ===========================================================================


def validate_graph(data: Any) -> ValidationResult:
    """Run the full validation pipeline on raw input.

    Pipeline stages:

    1. **Sanitize** — remove nulls, lowercase enums
    2. **Normalize** — map LLM aliases to canonical values
    3. **Auto-fix** — fill missing fields with defaults
    4. **Fatal checks** — invalid collections, missing project meta
    5. **Validate nodes** — Pydantic strict, drop broken
    6. **Validate edges** — Pydantic strict + referential integrity
    7. **Validate layers** — Pydantic strict, filter dangling nodeIds
    8. **Validate tour** — Pydantic strict, filter dangling nodeIds

    Returns ``ValidationResult`` with ``success=True`` and the cleaned graph,
    or ``success=False`` with issues and an optional ``fatal`` message.
    """
    # Tier 4: Fatal — not even an object
    if not isinstance(data, dict):
        fatal = "Invalid input: not an object"
        return ValidationResult(
            success=False,
            issues=[],
            fatal=fatal,
            errors=_build_errors([], fatal),
        )

    # Tier 1: Sanitize
    sanitized = sanitize_graph(data)

    # Normalize type aliases (existing pass from TS)
    normalized = normalize_graph(sanitized)

    # Tier 2: Auto-fix defaults and coercion
    fixed, issues = auto_fix_graph(normalized)

    # Tier 4: Fatal — malformed top-level collections
    required_collections = ("nodes", "edges", "layers", "tour")
    for collection in required_collections:
        val = fixed.get(collection)
        if val is not None and not isinstance(val, list):
            issue = _build_invalid_collection_issue(collection)
            issues.append(issue)
            return ValidationResult(
                success=False,
                errors=_build_errors(issues, issue.message),
                issues=issues,
                fatal=issue.message,
            )

    # Tier 4: Fatal — missing project metadata
    project_raw = fixed.get("project")
    if not isinstance(project_raw, dict):
        fatal_msg = "Missing or invalid project metadata"
        return ValidationResult(
            success=False,
            errors=_build_errors(issues, fatal_msg),
            issues=issues,
            fatal=fatal_msg,
        )

    try:
        project = ProjectMeta.model_validate(project_raw)
    except ValidationError:
        fatal_msg = "Missing or invalid project metadata"
        return ValidationResult(
            success=False,
            errors=_build_errors(issues, fatal_msg),
            issues=issues,
            fatal=fatal_msg,
        )

    # Tier 3: Validate nodes individually, drop broken
    valid_nodes: list[dict[str, Any]] = []
    if isinstance(fixed.get("nodes"), list):
        for i, node in enumerate(fixed["nodes"]):
            if not isinstance(node, dict):
                continue
            validated, issue = _validate_with_pydantic(GraphNode, node, i, "nodes")
            if validated is not None:
                valid_nodes.append(validated)
            elif issue is not None:
                issues.append(issue)

    # Tier 4: Fatal — no valid nodes
    if not valid_nodes:
        fatal_msg = "No valid nodes found in knowledge graph"
        return ValidationResult(
            success=False,
            errors=_build_errors(issues, fatal_msg),
            issues=issues,
            fatal=fatal_msg,
        )

    # Build node ID set for referential integrity
    node_ids: set[str] = {n["id"] for n in valid_nodes if isinstance(n.get("id"), str)}

    # Tier 3: Validate edges + referential integrity
    valid_edges: list[dict[str, Any]] = []
    if isinstance(fixed.get("edges"), list):
        for i, edge in enumerate(fixed["edges"]):
            if not isinstance(edge, dict):
                continue
            validated, issue = _validate_with_pydantic(GraphEdge, edge, i, "edges")
            if validated is None:
                if issue is not None:
                    issues.append(issue)
                continue
            # Referential integrity checks
            if validated["source"] not in node_ids:
                issues.append(GraphIssue(
                    level="dropped",
                    category="invalid-reference",
                    message=f'edges[{i}]: source "{validated["source"]}" does not exist in nodes — removed',
                    path=f"edges[{i}].source",
                ))
                continue
            if validated["target"] not in node_ids:
                issues.append(GraphIssue(
                    level="dropped",
                    category="invalid-reference",
                    message=f'edges[{i}]: target "{validated["target"]}" does not exist in nodes — removed',
                    path=f"edges[{i}].target",
                ))
                continue
            valid_edges.append(validated)

    # Validate layers (drop broken, filter dangling nodeIds)
    valid_layers: list[dict[str, Any]] = []
    if isinstance(fixed.get("layers"), list):
        for i, layer in enumerate(fixed["layers"]):
            if not isinstance(layer, dict):
                continue
            validated, issue = _validate_with_pydantic(Layer, layer, i, "layers")
            if validated is not None:
                validated["node_ids"] = [
                    nid for nid in validated["node_ids"] if nid in node_ids
                ]
                valid_layers.append(validated)
            elif issue is not None:
                issues.append(issue)

    # Validate tour steps (drop broken, filter dangling nodeIds)
    valid_tour: list[dict[str, Any]] = []
    if isinstance(fixed.get("tour"), list):
        for i, step in enumerate(fixed["tour"]):
            if not isinstance(step, dict):
                continue
            validated, issue = _validate_with_pydantic(TourStep, step, i, "tour")
            if validated is not None:
                validated["node_ids"] = [
                    nid for nid in validated["node_ids"] if nid in node_ids
                ]
                valid_tour.append(validated)
            elif issue is not None:
                issues.append(issue)

    # Build final graph dict
    version = fixed.get("version")
    graph: dict[str, Any] = {
        "version": version if isinstance(version, str) else "1.0.0",
        "project": project.model_dump(by_alias=False),
        "nodes": valid_nodes,
        "edges": valid_edges,
        "layers": valid_layers,
        "tour": valid_tour,
    }

    return ValidationResult(
        success=True,
        data=graph,
        issues=issues,
        errors=_build_errors(issues),
    )
