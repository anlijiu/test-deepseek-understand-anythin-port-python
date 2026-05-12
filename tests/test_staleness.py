"""Tests for analysis/staleness.py — port of staleness.test.ts."""

from __future__ import annotations

import subprocess
from unittest import mock

from understand_anything.analysis.staleness import (
    get_changed_files,
    is_stale,
    merge_graph_update,
)
from understand_anything.types import (
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    Layer,
    ProjectMeta,
    TourStep,
)


def _make_node(overrides: dict | None = None) -> GraphNode:
    defaults: dict = {
        "id": "file-a",
        "type": "file",
        "name": "a.ts",
        "summary": "",
        "tags": [],
        "complexity": "simple",
    }
    merged = {**defaults, **(overrides or {})}
    file_path = merged.pop("filePath", None)
    node = GraphNode(**merged)
    if file_path is not None:
        node.file_path = file_path
    return node


def _make_edge(overrides: dict | None = None) -> GraphEdge:
    defaults: dict = {
        "source": "file-a",
        "target": "file-b",
        "type": "imports",
        "direction": "forward",
        "weight": 1.0,
    }
    return GraphEdge(**{**defaults, **(overrides or {})})


def _make_graph(overrides: dict | None = None) -> KnowledgeGraph:
    defaults: dict = {
        "version": "1.0.0",
        "project": ProjectMeta(
            name="test-project",
            languages=["typescript"],
            frameworks=[],
            description="A test project",
            analyzedAt="2026-01-01T00:00:00.000Z",
            gitCommitHash="abc123",
        ),
        "nodes": [],
        "edges": [],
        "layers": [],
        "tour": [],
    }
    merged = {**defaults, **(overrides or {})}
    return KnowledgeGraph(**merged)


class TestGetChangedFiles:
    """Port of describe('getChangedFiles', ...)."""

    def test_returns_changed_file_list_from_git_diff(self) -> None:
        with mock.patch("subprocess.check_output") as mock_check:
            mock_check.return_value = "src/index.ts\nsrc/utils.ts\n"
            result = get_changed_files("/project", "abc123")
            assert result == ["src/index.ts", "src/utils.ts"]
            mock_check.assert_called_once_with(
                ["git", "diff", "abc123..HEAD", "--name-only"],
                cwd="/project",
                text=True,
                stderr=mock.ANY,
            )

    def test_returns_empty_array_when_no_changes(self) -> None:
        with mock.patch("subprocess.check_output") as mock_check:
            mock_check.return_value = ""
            result = get_changed_files("/project", "abc123")
            assert result == []

    def test_returns_empty_array_on_git_error(self) -> None:
        with mock.patch("subprocess.check_output") as mock_check:
            mock_check.side_effect = subprocess.CalledProcessError(
                128, "git", stderr=b"fatal: bad revision"
            )
            result = get_changed_files("/project", "abc123")
            assert result == []


class TestIsStale:
    """Port of describe('isStale', ...)."""

    def test_returns_stale_when_files_have_changed(self) -> None:
        with mock.patch("subprocess.check_output") as mock_check:
            mock_check.return_value = "src/index.ts\n"
            result = is_stale("/project", "abc123")
            assert result == (True, ["src/index.ts"])

    def test_returns_not_stale_when_no_files_changed(self) -> None:
        with mock.patch("subprocess.check_output") as mock_check:
            mock_check.return_value = ""
            result = is_stale("/project", "abc123")
            assert result == (False, [])


class TestMergeGraphUpdate:
    """Port of describe('mergeGraphUpdate', ...)."""

    def test_replaces_nodes_for_changed_files(self) -> None:
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts", "summary": "Old summary"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts", "summary": "Unchanged"}),
                _make_node({"id": "func-a1", "name": "funcA1", "type": "function", "filePath": "src/a.ts", "summary": "Old function"}),
            ],
        })

        new_nodes = [
            _make_node({"id": "file-a-v2", "name": "a.ts", "filePath": "src/a.ts", "summary": "New summary"}),
            _make_node({"id": "func-a2", "name": "funcA2", "type": "function", "filePath": "src/a.ts", "summary": "New function"}),
        ]

        result = merge_graph_update(
            existing_graph, ["src/a.ts"], new_nodes, [], "def456"
        )

        # Old nodes from src/a.ts should be gone
        assert not any(n.id == "file-a" for n in result.nodes)
        assert not any(n.id == "func-a1" for n in result.nodes)
        # New nodes should be present
        assert any(n.id == "file-a-v2" for n in result.nodes)
        assert any(n.id == "func-a2" for n in result.nodes)
        # Unchanged file should remain
        assert any(n.id == "file-b" for n in result.nodes)

    def test_removes_edges_originating_from_and_targeting_changed_files(
        self,
    ) -> None:
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts"}),
                _make_node({"id": "file-c", "name": "c.ts", "filePath": "src/c.ts"}),
            ],
            "edges": [
                _make_edge({"source": "file-a", "target": "file-b", "type": "imports"}),
                _make_edge({"source": "file-b", "target": "file-c", "type": "imports"}),
                _make_edge({"source": "file-c", "target": "file-a", "type": "imports"}),
            ],
        })

        new_nodes = [
            _make_node({"id": "file-a-v2", "name": "a.ts", "filePath": "src/a.ts", "summary": "Updated"}),
        ]
        new_edges = [
            _make_edge({"source": "file-a-v2", "target": "file-c", "type": "imports"}),
        ]

        result = merge_graph_update(
            existing_graph, ["src/a.ts"], new_nodes, new_edges, "def456"
        )

        # Old edge from file-a should be removed
        assert not any(e.source == "file-a" and e.target == "file-b" for e in result.edges)
        # Edge between unchanged files should remain
        assert any(e.source == "file-b" and e.target == "file-c" for e in result.edges)
        # Edge targeting a removed node (file-a) should be removed
        assert not any(e.source == "file-c" and e.target == "file-a" for e in result.edges)
        # New edge should be added
        assert any(e.source == "file-a-v2" and e.target == "file-c" for e in result.edges)

    def test_cleans_layer_node_ids_after_merge(self) -> None:
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts"}),
                _make_node({"id": "func-a", "name": "funcA", "type": "function", "filePath": "src/a.ts"}),
            ],
            "layers": [
                Layer(id="layer-1", name="Core", description="Core layer", nodeIds=["file-a", "file-b", "func-a"]),
            ],
        })

        result = merge_graph_update(
            existing_graph, ["src/a.ts"], [], [], "def456"
        )

        assert len(result.layers) == 1
        assert result.layers[0].node_ids == ["file-b"]

    def test_cleans_tour_node_ids_after_merge(self) -> None:
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts"}),
                _make_node({"id": "func-a", "name": "funcA", "type": "function", "filePath": "src/a.ts"}),
            ],
            "tour": [
                TourStep(order=1, title="Start", description="Start here", nodeIds=["file-a", "file-b", "func-a"]),
            ],
        })

        result = merge_graph_update(
            existing_graph, ["src/a.ts"], [], [], "def456"
        )

        assert len(result.tour) == 1
        assert result.tour[0].node_ids == ["file-b"]

    def test_accepts_updated_layers_and_tour(self) -> None:
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts"}),
            ],
            "layers": [
                Layer(id="old-layer", name="Old", description="Old", nodeIds=["file-a"]),
            ],
            "tour": [
                TourStep(order=1, title="Old", description="Old", nodeIds=["file-a"]),
            ],
        })

        updated_layers = [
            Layer(id="new-layer", name="New", description="New", nodeIds=["file-b", "file-a"]),
        ]
        updated_tour = [
            TourStep(order=1, title="New", description="New", nodeIds=["file-b", "file-a"]),
        ]

        result = merge_graph_update(
            existing_graph,
            ["src/a.ts"],
            [],
            [],
            "def456",
            updated_layers=updated_layers,
            updated_tour=updated_tour,
        )

        assert len(result.layers) == 1
        assert result.layers[0].id == "new-layer"
        assert result.layers[0].node_ids == ["file-b"]

        assert len(result.tour) == 1
        assert result.tour[0].title == "New"
        assert result.tour[0].node_ids == ["file-b"]

    def test_preserves_layer_refs_when_new_nodes_reuse_ids(self) -> None:
        """Regression: new nodes often reuse stable path-based IDs.

        When a changed file is re-analysed, graph builder produces nodes with
        the same IDs (e.g. ``file:src/a.ts``, ``function:src/a.ts:foo``).
        Layer/tour references to those IDs must survive the merge.
        """
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file:src/a.py", "name": "a.py", "filePath": "src/a.py", "summary": "Old"}),
                _make_node({"id": "file:src/b.py", "name": "b.py", "filePath": "src/b.py", "summary": "Stable"}),
            ],
            "layers": [
                Layer(id="layer-1", name="Core", description="Core", nodeIds=["file:src/a.py", "file:src/b.py"]),
            ],
            "tour": [
                TourStep(order=1, title="Start", description="Start here", nodeIds=["file:src/a.py"]),
            ],
        })

        # New node reuses the same stable ID
        new_nodes = [
            _make_node({"id": "file:src/a.py", "name": "a.py", "filePath": "src/a.py", "summary": "Updated"}),
        ]

        result = merge_graph_update(
            existing_graph, ["src/a.py"], new_nodes, [], "def456"
        )

        # Reused ID must still be in the final graph
        file_ids = {n.id for n in result.nodes}
        assert "file:src/a.py" in file_ids
        assert "file:src/b.py" in file_ids

        # Layer must retain the reused ID
        assert result.layers[0].node_ids == ["file:src/a.py", "file:src/b.py"]

        # Tour must retain the reused ID
        assert result.tour[0].node_ids == ["file:src/a.py"]

    def test_preserves_incoming_edges_when_new_nodes_reuse_ids(self) -> None:
        """Incoming edges from unchanged nodes survive stable-ID replacement."""
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file:src/a.py", "name": "a.py", "filePath": "src/a.py", "summary": "Old"}),
                _make_node({"id": "file:src/b.py", "name": "b.py", "filePath": "src/b.py", "summary": "Stable"}),
            ],
            "edges": [
                _make_edge({
                    "source": "file:src/b.py",
                    "target": "file:src/a.py",
                    "type": "imports",
                }),
            ],
        })

        new_nodes = [
            _make_node({"id": "file:src/a.py", "name": "a.py", "filePath": "src/a.py", "summary": "Updated"}),
        ]

        result = merge_graph_update(
            existing_graph, ["src/a.py"], new_nodes, [], "def456"
        )

        assert [
            (edge.source, edge.target) for edge in result.edges
        ] == [("file:src/b.py", "file:src/a.py")]

    def test_drops_edges_targeting_removed_nodes_after_merge(self) -> None:
        """Edges targeting changed nodes are dropped when no replacement exists."""
        existing_graph = _make_graph({
            "nodes": [
                _make_node({"id": "file-a", "name": "a.ts", "filePath": "src/a.ts"}),
                _make_node({"id": "file-b", "name": "b.ts", "filePath": "src/b.ts"}),
            ],
            "edges": [
                _make_edge({"source": "file-b", "target": "file-a", "type": "imports"}),
            ],
        })

        result = merge_graph_update(
            existing_graph, ["src/a.ts"], [], [], "def456"
        )

        assert result.edges == []

    def test_updates_analyzed_at_timestamp_and_git_commit_hash(self) -> None:
        from datetime import datetime, timezone

        existing_graph = _make_graph()
        before = datetime.now(timezone.utc).isoformat()

        result = merge_graph_update(existing_graph, [], [], [], "def456")

        after = datetime.now(timezone.utc).isoformat()

        assert result.project.git_commit_hash == "def456"
        assert result.project.analyzed_at >= before
        assert result.project.analyzed_at <= after
