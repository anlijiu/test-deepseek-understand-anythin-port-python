"""Git diff wrapper — detect and merge knowledge graph changes.

Python port of the TypeScript ``staleness.ts``.  Checks which files changed
since a known commit and performs incremental graph updates.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from understand_anything.types import (  # noqa: TC001
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    Layer,
    TourStep,
)


def get_changed_files(
    project_dir: str,
    last_commit_hash: str,
) -> list[str]:
    """Get the list of files that changed between *last_commit_hash* and HEAD.

    Returns an empty list on error or when there are no changes.
    """
    try:
        output = subprocess.check_output(
            ["git", "diff", f"{last_commit_hash}..HEAD", "--name-only"],  # noqa: S607
            cwd=project_dir,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [line.strip() for line in output.split("\n") if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def is_stale(
    project_dir: str,
    last_commit_hash: str,
) -> tuple[bool, list[str]]:
    """Check whether the knowledge graph is stale relative to HEAD.

    Returns a ``(stale, changed_files)`` tuple.
    """
    changed_files = get_changed_files(project_dir, last_commit_hash)
    return bool(changed_files), changed_files


def merge_graph_update(
    existing_graph: KnowledgeGraph,
    changed_file_paths: list[str],
    new_nodes: list[GraphNode],
    new_edges: list[GraphEdge],
    new_commit_hash: str,
    updated_layers: list[Layer] | None = None,
    updated_tour: list[TourStep] | None = None,
) -> KnowledgeGraph:
    """Merge new analysis results into an existing knowledge graph.

    1. Remove old nodes belonging to changed files (matched by filePath).
    2. Remove old edges where the source or target is a removed node.
    3. Add new nodes and edges.
    4. Update project timestamp and commit hash.
    5. Clean dangling node references from layers and tour steps.
    """
    changed_set = set(changed_file_paths)

    # Collect IDs of nodes that belong to changed files (will be removed)
    removed_node_ids: set[str] = {
        node.id
        for node in existing_graph.nodes
        if node.file_path is not None and node.file_path in changed_set
    }

    # Keep nodes that don't belong to changed files
    retained_nodes = [
        n for n in existing_graph.nodes if n.id not in removed_node_ids
    ]
    final_nodes = [*retained_nodes, *new_nodes]
    valid_node_ids = {n.id for n in final_nodes}

    # Keep existing edges from unchanged sources when both endpoints still exist.
    # Edges originating from changed nodes are replaced by new_edges.
    retained_edges = [
        e
        for e in existing_graph.edges
        if e.source not in removed_node_ids
        and e.source in valid_node_ids
        and e.target in valid_node_ids
    ]
    final_edges = [
        e
        for e in [*retained_edges, *new_edges]
        if e.source in valid_node_ids and e.target in valid_node_ids
    ]

    # Build updated project metadata
    updated_project = existing_graph.project.model_copy(
        update={
            "git_commit_hash": new_commit_hash,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Clean layers: keep only references to nodes that actually exist
    source_layers = (
        updated_layers if updated_layers is not None else existing_graph.layers
    )
    final_layers = []
    for layer in source_layers:
        cleaned_ids = [
            nid for nid in layer.node_ids if nid in valid_node_ids
        ]
        final_layers.append(
            layer.model_copy(update={"node_ids": cleaned_ids})
        )

    # Clean tour: keep only references to nodes that actually exist
    source_tour = (
        updated_tour if updated_tour is not None else existing_graph.tour
    )
    final_tour = []
    for step in source_tour:
        cleaned_ids = [
            nid for nid in step.node_ids if nid in valid_node_ids
        ]
        final_tour.append(
            step.model_copy(update={"node_ids": cleaned_ids})
        )

    return KnowledgeGraph(
        version=existing_graph.version,
        kind=existing_graph.kind,
        project=updated_project,
        nodes=final_nodes,
        edges=final_edges,
        layers=final_layers,
        tour=final_tour,
    )
