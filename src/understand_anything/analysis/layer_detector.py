"""Heuristic + LLM architectural layer detection.

Python port of the TypeScript ``layer-detector.ts``. Assigns file nodes to
logical architectural layers — first via heuristic directory-pattern matching,
then optionally via LLM refinement.
"""

from __future__ import annotations

import json
import re
from typing import Any

from understand_anything.types import KnowledgeGraph, Layer  # noqa: TC001

# ===========================================================================
# Directory-pattern → layer-name mapping for heuristic detection.
# Order matters: first match wins.
# ===========================================================================

_LAYER_PATTERNS: list[dict[str, Any]] = [
    {
        "patterns": ["routes", "controller", "handler", "endpoint", "api"],
        "layerName": "API Layer",
        "description": "HTTP endpoints, route handlers, and API controllers",
    },
    {
        "patterns": ["service", "usecase", "use-case", "business"],
        "layerName": "Service Layer",
        "description": "Business logic and application services",
    },
    {
        "patterns": [
            "model", "entity", "schema", "database", "db", "migration",
            "repository", "repo",
        ],
        "layerName": "Data Layer",
        "description": "Data models, database access, and persistence",
    },
    {
        "patterns": [
            "component", "view", "page", "screen", "layout", "widget", "ui",
        ],
        "layerName": "UI Layer",
        "description": "User interface components and views",
    },
    {
        "patterns": ["middleware", "interceptor", "guard", "filter", "pipe"],
        "layerName": "Middleware Layer",
        "description": "Request/response middleware and interceptors",
    },
    {
        "patterns": ["client", "integration", "external", "sdk", "vendor", "adapter"],
        "layerName": "External Services",
        "description": "External service integrations, SDKs, and third-party adapters",
    },
    {
        "patterns": [
            "worker", "job", "queue", "cron", "consumer", "processor",
            "scheduler", "background",
        ],
        "layerName": "Background Tasks",
        "description": "Background workers, job processors, and scheduled tasks",
    },
    {
        "patterns": ["util", "helper", "lib", "common", "shared"],
        "layerName": "Utility Layer",
        "description": "Shared utilities, helpers, and common libraries",
    },
    {
        "patterns": ["test", "spec", "__test__", "__spec__", "__tests__", "__specs__"],
        "layerName": "Test Layer",
        "description": "Test files and test utilities",
    },
    {
        "patterns": ["config", "setting", "env"],
        "layerName": "Configuration Layer",
        "description": "Application configuration and environment settings",
    },
]


def _to_layer_id(name: str) -> str:
    """Convert a layer name to a kebab-case layer ID."""
    return f"layer:{name.lower().replace(' ', '-')}"


def _match_file_to_layer(file_path: str) -> str | None:
    """Determine which layer a file path belongs to based on directory patterns.

    Normalises path separators and checks each directory segment against
    the known layer patterns (including plural forms).
    """
    normalized = file_path.replace("\\", "/").lower()
    segments = normalized.split("/")

    for entry in _LAYER_PATTERNS:
        for pattern in entry["patterns"]:
            for segment in segments:
                if segment == pattern or segment == pattern + "s":
                    return str(entry["layerName"])

    return None


# ===========================================================================
# Heuristic layer detection
# ===========================================================================


def detect_layers(graph: KnowledgeGraph) -> list[Layer]:
    """Heuristic layer detection — assigns file nodes to layers based on
    directory path patterns.  Unmatched files go to a "Core" layer.

    Only ``file``-type nodes are assigned to layers.
    """
    layer_map: dict[str, list[str]] = {}

    for node in graph.nodes:
        if node.type != "file":
            continue
        if node.file_path:
            layer_name = _match_file_to_layer(node.file_path) or "Core"
        else:
            layer_name = "Core"
        layer_map.setdefault(layer_name, []).append(node.id)

    layers: list[Layer] = []
    for name, node_ids in layer_map.items():
        if name == "Core":
            description = "Core application files"
        else:
            description = (
                next(
                    (
                        p["description"]
                        for p in _LAYER_PATTERNS
                        if p["layerName"] == name
                    ),
                    "",
                )
            )
        layers.append(
            Layer(
                id=_to_layer_id(name),
                name=name,
                description=description,
                nodeIds=node_ids,
            )
        )

    return layers


# ===========================================================================
# LLM prompt building / response parsing
# ===========================================================================


def build_layer_detection_prompt(graph: KnowledgeGraph) -> str:
    """Build an LLM prompt that asks the model to identify logical layers
    from the file paths in the knowledge graph.
    """
    file_paths = [
        n.file_path
        for n in graph.nodes
        if n.type == "file" and n.file_path
    ]
    file_list_str = "\n".join(f"  - {f}" for f in file_paths)

    return (
        "You are a software architecture analyst. Given the following list"
        " of file paths from a codebase, identify the logical architectural"
        " layers.\n\n"
        f"File paths:\n{file_list_str}\n\n"
        "Return a JSON array of 3-7 layers. Each layer object must have:\n"
        '- "name": A short layer name (e.g., "API", "Data", "UI")\n'
        '- "description": What this layer is responsible for (1 sentence)\n'
        '- "filePatterns": An array of path prefixes that belong to this'
        ' layer (e.g., ["src/routes/", "src/controllers/"])\n\n'
        "Every file should belong to exactly one layer. Use the most"
        " specific pattern possible.\n\n"
        "Respond ONLY with the JSON array, no additional text."
    )


def parse_layer_detection_response(
    response: str,
) -> list[dict[str, Any]] | None:
    """Parse an LLM response for layer detection.

    Handles markdown code fences and raw JSON arrays.
    Returns the parsed list or ``None`` on failure.
    """
    if not response or response.strip() == "":
        return None

    try:
        # Extract from markdown code fences
        fence_match = re.search(
            r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", response
        )
        json_str = fence_match.group(1).strip() if fence_match else response.strip()

        # Find a JSON array
        array_match = re.search(r"\[[\s\S]*\]", json_str)
        if not array_match:
            return None

        parsed = json.loads(array_match.group(0))

        if not isinstance(parsed, list) or len(parsed) == 0:
            return None

        layers: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            desc = item.get("description", "")
            patterns = item.get("filePatterns", [])
            layers.append(
                {
                    "name": name,
                    "description": desc if isinstance(desc, str) else "",
                    "filePatterns": (
                        [p for p in patterns if isinstance(p, str)]
                        if isinstance(patterns, list)
                        else []
                    ),
                }
            )

    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    else:
        return layers or None


# ===========================================================================
# LLM layer application
# ===========================================================================


def apply_llm_layers(
    graph: KnowledgeGraph,
    llm_layers: list[dict[str, Any]],
) -> list[Layer]:
    """Apply LLM-provided layer definitions to a knowledge graph.

    Matches file nodes against LLM ``filePatterns`` (path prefix matching).
    Unassigned file nodes go to an "Other" layer.
    """
    layer_map: dict[str, list[str]] = {}

    # Initialise all LLM layers
    for llm_layer in llm_layers:
        layer_map[str(llm_layer["name"])] = []

    for node in graph.nodes:
        if node.type != "file":
            continue

        if not node.file_path:
            layer_map.setdefault("Other", []).append(node.id)
            continue

        normalized = node.file_path.replace("\\", "/")
        assigned = False

        for llm_layer in llm_layers:
            for pattern in llm_layer.get("filePatterns", []):
                if not isinstance(pattern, str):
                    continue
                if normalized.startswith(pattern) or ("/" + pattern) in normalized:
                    name = str(llm_layer["name"])
                    layer_map.setdefault(name, []).append(node.id)
                    assigned = True
                    break
            if assigned:
                break

        if not assigned:
            layer_map.setdefault("Other", []).append(node.id)

    layers: list[Layer] = []
    for name, node_ids in layer_map.items():
        if not node_ids:
            continue
        matching = [
            entry for entry in llm_layers if entry.get("name") == name
        ]
        found: dict[str, Any] | None = matching[0] if matching else None
        description = (
            found.get("description", "Uncategorized files")
            if found
            else "Uncategorized files"
        )
        layers.append(
            Layer(
                id=_to_layer_id(name),
                name=name,
                description=description if isinstance(description, str) else "",
                nodeIds=node_ids,
            )
        )

    return layers
