"""Kahn's algorithm + LLM guided tour generation.

Python port of the TypeScript ``tour-generator.ts``.  Generates a guided tour
of a knowledge graph that helps newcomers understand the codebase step by
step.  Two strategies are available:

1. **Heuristic** (:func:`generate_heuristic_tour`) — topological sort via
   Kahn's algorithm, batched by layer or fixed group size.
2. **LLM** — prompt the LLM to produce tour steps from project metadata.
"""

from __future__ import annotations

import json
import re
from typing import Any

from understand_anything.types import KnowledgeGraph, TourStep  # noqa: TC001

# ===========================================================================
# LLM prompt building
# ===========================================================================


def build_tour_generation_prompt(graph: KnowledgeGraph) -> str:
    """Build an LLM prompt asking for a guided tour of the project.

    Includes project metadata, node summaries, edges (up to 50), and
    layer information.
    """
    project = graph.project
    nodes = graph.nodes
    edges = graph.edges
    layers = graph.layers

    node_list = "\n".join(
        f"  - [{n.type}] {n.name}"
        f"{f' ({n.file_path})' if n.file_path else ''}"
        f": {n.summary}"
        for n in nodes
    )

    edge_list = "\n".join(
        f"  - {e.source} --{e.type}--> {e.target}"
        for e in edges[:50]
    )

    if layers:
        layer_list_str = "\n".join(
            f"  - {lyr.name}: {lyr.description}"
            f" (nodes: {', '.join(lyr.node_ids)})"
            for lyr in layers
        )
    else:
        layer_list_str = "  (no layers detected)"

    return (
        "You are a software architecture educator. Generate a guided tour"
        " of the following project that helps a newcomer understand the"
        " codebase step by step.\n\n"
        f"Project: {project.name}\n"
        f"Description: {project.description}\n"
        f"Languages: {', '.join(project.languages)}\n"
        f"Frameworks: {', '.join(project.frameworks)}\n\n"
        f"Nodes:\n{node_list}\n\n"
        f"Edges (dependencies/relationships):\n{edge_list}\n\n"
        f"Layers:\n{layer_list_str}\n\n"
        "Create a logical tour that:\n"
        "1. Starts with entry points or high-level overview files\n"
        "2. Follows the natural dependency flow\n"
        "3. Groups related files together\n"
        "4. Ends with supporting utilities or concepts\n\n"
        'Return a JSON object with a "steps" array. Each step must have:\n'
        '- "order": sequential number starting from 1\n'
        '- "title": a short descriptive title for this tour stop\n'
        '- "description": 2-3 sentences explaining what the reader will'
        " learn at this step\n"
        '- "nodeIds": array of node IDs to highlight for this step\n'
        '- "languageLesson" (optional): a brief note about language-specific'
        " patterns seen in these files\n\n"
        "Respond ONLY with the JSON object, no additional text."
    )


# ===========================================================================
# LLM response parsing
# ===========================================================================


def parse_tour_generation_response(response: str) -> list[TourStep]:
    """Parse an LLM response for tour generation.

    Handles raw JSON and JSON wrapped in markdown code fences.
    Filters out steps missing required fields.
    Returns empty list if parsing fails.
    """
    if not response or response.strip() == "":
        return []

    try:
        fence_match = re.search(
            r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", response
        )
        json_str = fence_match.group(1).strip() if fence_match else response.strip()

        object_match = re.search(r"\{[\s\S]*\}", json_str)
        if not object_match:
            return []

        parsed = json.loads(object_match.group(0))

        if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
            return []

        steps: list[TourStep] = []
        for item in parsed["steps"]:
            if not isinstance(item, dict):
                continue
            order = item.get("order")
            title = item.get("title")
            description = item.get("description")
            node_ids = item.get("nodeIds")

            if not isinstance(order, (int, float)):
                continue
            if not isinstance(title, str) or len(title) == 0:
                continue
            if not isinstance(description, str) or len(description) == 0:
                continue
            if not isinstance(node_ids, list) or len(node_ids) == 0:
                continue

            step = TourStep(
                order=int(order),
                title=title,
                description=description,
                nodeIds=[str(nid) for nid in node_ids if isinstance(nid, str)],
            )

            lang_lesson = item.get("languageLesson")
            if isinstance(lang_lesson, str):
                step.language_lesson = lang_lesson

            steps.append(step)

    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    else:
        return steps


# ===========================================================================
# Heuristic tour generation (Kahn's algorithm)
# ===========================================================================


def generate_heuristic_tour(graph: KnowledgeGraph) -> list[TourStep]:
    """Generate a tour heuristically (without an LLM) using graph topology.

    Strategy:

    1. Separate concept nodes from code nodes.
    2. Build adjacency info from edges.
    3. Find entry points (nodes with 0 incoming edges).
    4. Topological sort via Kahn's algorithm.
    5. If layers exist: group by layer in topological order.
    6. If no layers: batch by 3 nodes per step.
    7. Add concept nodes as a final "Key Concepts" step.
    8. Assign sequential order numbers.
    """
    nodes = graph.nodes
    edges = graph.edges
    layers = graph.layers

    # Separate concept nodes from code nodes
    concept_nodes = [n for n in nodes if n.type == "concept"]
    code_nodes = [n for n in nodes if n.type != "concept"]
    code_node_ids: set[str] = {n.id for n in code_nodes}

    # Build adjacency info (only for code nodes)
    in_degree: dict[str, int] = {n.id: 0 for n in code_nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in code_nodes}

    for edge in edges:
        if edge.source not in code_node_ids or edge.target not in code_node_ids:
            continue
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1
        adjacency.setdefault(edge.source, []).append(edge.target)

    # Kahn's algorithm for topological sort
    queue: list[str] = [
        node_id for node_id, deg in in_degree.items() if deg == 0
    ]

    topo_order: list[str] = []
    while queue:
        current = queue.pop(0)
        topo_order.append(current)

        for neighbor in adjacency.get(current, []):
            new_deg = in_degree.get(neighbor, 1) - 1
            in_degree[neighbor] = new_deg
            if new_deg == 0:
                queue.append(neighbor)

    # Add any nodes not reached by topological sort (isolated nodes / cycles)
    for node in code_nodes:
        if node.id not in topo_order:
            topo_order.append(node.id)

    # Build tour steps
    steps: list[TourStep] = []
    node_map: dict[str, Any] = {n.id: n for n in nodes}

    if layers:
        # Group by layer in topological order
        node_to_layer: dict[str, str] = {}
        for layer in layers:
            for node_id in layer.node_ids:
                node_to_layer[node_id] = layer.id

        # Determine the order layers are first encountered
        layer_order: list[str] = []
        layer_nodes: dict[str, list[str]] = {}

        for node_id in topo_order:
            lid = node_to_layer.get(node_id)
            if lid:
                if lid not in layer_nodes:
                    layer_nodes[lid] = []
                    layer_order.append(lid)
                layer_nodes[lid].append(node_id)

        # Create steps for each layer
        layer_map = {lyr.id: lyr for lyr in layers}
        for lid in layer_order:
            lyr = layer_map.get(lid)
            nids = layer_nodes.get(lid, [])
            if lyr and nids:
                node_summaries = ", ".join(
                    str(node_map[nid].name)
                    for nid in nids
                    if nid in node_map
                )
                steps.append(
                    TourStep(
                        order=0,  # assigned later
                        title=lyr.name,
                        description=(
                            f"{lyr.description}. Key files: {node_summaries}."
                        ),
                        nodeIds=nids,
                    )
                )

        # Add unlayered code nodes as "Supporting Components"
        layered_node_ids: set[str] = set()
        for lyr in layers:
            layered_node_ids.update(lyr.node_ids)
        unlayered = [
            nid for nid in topo_order if nid not in layered_node_ids
        ]
        if unlayered:
            node_summaries = ", ".join(
                str(node_map[nid].name)
                for nid in unlayered
                if nid in node_map
            )
            steps.append(
                TourStep(
                    order=0,
                    title="Supporting Components",
                    description=(
                        f"Additional supporting files: {node_summaries}."
                    ),
                    nodeIds=unlayered,
                )
            )
    else:
        # No layers: batch by 3 nodes per step
        for i in range(0, len(topo_order), 3):
            batch = topo_order[i : i + 3]
            node_summaries = "; ".join(
                f"{node_map[nid].name} ({node_map[nid].summary})"
                if nid in node_map
                else nid
                for nid in batch
            )
            step_num = i // 3 + 1
            steps.append(
                TourStep(
                    order=0,  # assigned later
                    title=f"Step {step_num}: Code Walkthrough",
                    description=f"Exploring: {node_summaries}.",
                    nodeIds=batch,
                )
            )

    # Add concept nodes as final step if any exist
    if concept_nodes:
        concept_summaries = "; ".join(
            f"{n.name} ({n.summary})" for n in concept_nodes
        )
        steps.append(
            TourStep(
                order=0,
                title="Key Concepts",
                description=(
                    f"Important architectural concepts: {concept_summaries}."
                ),
                nodeIds=[n.id for n in concept_nodes],
            )
        )

    # Assign sequential order numbers
    for i, step in enumerate(steps):
        step.order = i + 1

    return steps
