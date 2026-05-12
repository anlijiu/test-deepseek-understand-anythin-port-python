"""Tests for analysis/normalize.py — port of normalize-graph.test.ts."""

from __future__ import annotations

from understand_anything.analysis.normalize import (
    normalize_batch_output,
    normalize_complexity,
    normalize_node_id,
)
from understand_anything.schema import validate_graph


class TestNormalizeNodeId:
    """Port of describe('normalizeNodeId', ...)."""

    def test_passes_through_a_correct_file_id_unchanged(self) -> None:
        assert (
            normalize_node_id("file:src/index.ts", {"type": "file"})
            == "file:src/index.ts"
        )

    def test_passes_through_a_correct_func_id_unchanged(self) -> None:
        assert (
            normalize_node_id(
                "func:src/utils.ts:formatDate", {"type": "function"}
            )
            == "func:src/utils.ts:formatDate"
        )

    def test_passes_through_a_correct_class_id_unchanged(self) -> None:
        assert (
            normalize_node_id(
                "class:src/models/User.ts:User", {"type": "class"}
            )
            == "class:src/models/User.ts:User"
        )

    def test_fixes_double_prefixed_ids(self) -> None:
        assert (
            normalize_node_id("file:file:src/foo.ts", {"type": "file"})
            == "file:src/foo.ts"
        )

    def test_strips_project_name_prefix_when_valid_prefix_follows(self) -> None:
        assert (
            normalize_node_id(
                "my-project:file:src/foo.ts", {"type": "file"}
            )
            == "file:src/foo.ts"
        )

    def test_strips_project_name_prefix_and_adds_correct_prefix_for_bare_path(
        self,
    ) -> None:
        assert (
            normalize_node_id("my-project:src/foo.ts", {"type": "file"})
            == "file:src/foo.ts"
        )

    def test_adds_file_prefix_to_bare_paths(self) -> None:
        assert (
            normalize_node_id(
                "frontend/src/utils/constants.ts", {"type": "file"}
            )
            == "file:frontend/src/utils/constants.ts"
        )

    def test_reconstructs_func_id_from_file_path_and_name_for_bare_paths(
        self,
    ) -> None:
        assert (
            normalize_node_id(
                "formatDate",
                {
                    "type": "function",
                    "filePath": "src/utils.ts",
                    "name": "formatDate",
                },
            )
            == "func:src/utils.ts:formatDate"
        )

    def test_reconstructs_class_id_from_file_path_and_name_for_bare_paths(
        self,
    ) -> None:
        assert (
            normalize_node_id(
                "User",
                {
                    "type": "class",
                    "filePath": "src/models/User.ts",
                    "name": "User",
                },
            )
            == "class:src/models/User.ts:User"
        )

    def test_trims_whitespace(self) -> None:
        assert (
            normalize_node_id("  file:src/foo.ts  ", {"type": "file"})
            == "file:src/foo.ts"
        )

    def test_handles_module_and_concept_prefixes(self) -> None:
        assert (
            normalize_node_id("module:auth", {"type": "module"})
            == "module:auth"
        )
        assert (
            normalize_node_id("concept:caching", {"type": "concept"})
            == "concept:caching"
        )

    def test_handles_project_name_prefix_before_a_valid_non_code_prefix(
        self,
    ) -> None:
        assert (
            normalize_node_id(
                "my-project:service:docker-compose.yml", {"type": "file"}
            )
            == "service:docker-compose.yml"
        )

    def test_returns_empty_string_for_empty_input(self) -> None:
        assert normalize_node_id("", {"type": "file"}) == ""

    def test_falls_back_to_untouched_id_for_unknown_node_type(self) -> None:
        # Unknown type "widget" — no TYPE_TO_PREFIX mapping
        assert normalize_node_id("some-id", {"type": "widget"}) == "some-id"

    def test_passes_through_non_code_type_ids_unchanged(self) -> None:
        assert (
            normalize_node_id("config:tsconfig.json", {"type": "config"})
            == "config:tsconfig.json"
        )
        assert (
            normalize_node_id("document:README.md", {"type": "document"})
            == "document:README.md"
        )
        assert (
            normalize_node_id(
                "service:docker-compose.yml", {"type": "service"}
            )
            == "service:docker-compose.yml"
        )
        assert (
            normalize_node_id(
                "table:migrations/001.sql:users", {"type": "table"}
            )
            == "table:migrations/001.sql:users"
        )
        assert (
            normalize_node_id(
                "endpoint:src/routes.ts:GET /api/users", {"type": "endpoint"}
            )
            == "endpoint:src/routes.ts:GET /api/users"
        )
        assert (
            normalize_node_id(
                "pipeline:.github/workflows/ci.yml", {"type": "pipeline"}
            )
            == "pipeline:.github/workflows/ci.yml"
        )
        assert (
            normalize_node_id("schema:schema.graphql", {"type": "schema"})
            == "schema:schema.graphql"
        )
        assert (
            normalize_node_id("resource:main.tf", {"type": "resource"})
            == "resource:main.tf"
        )

    def test_adds_prefix_for_bare_paths_with_non_code_types(self) -> None:
        assert (
            normalize_node_id("tsconfig.json", {"type": "config"})
            == "config:tsconfig.json"
        )
        assert (
            normalize_node_id("README.md", {"type": "document"})
            == "document:README.md"
        )

    def test_strips_project_name_prefix_from_non_code_type_ids(self) -> None:
        assert (
            normalize_node_id(
                "my-project:config:tsconfig.json", {"type": "config"}
            )
            == "config:tsconfig.json"
        )


class TestNormalizeComplexity:
    """Port of describe('normalizeComplexity', ...)."""

    def test_passes_through_valid_values_unchanged(self) -> None:
        assert normalize_complexity("simple") == "simple"
        assert normalize_complexity("moderate") == "moderate"
        assert normalize_complexity("complex") == "complex"

    def test_maps_low_to_simple(self) -> None:
        assert normalize_complexity("low") == "simple"

    def test_maps_high_to_complex(self) -> None:
        assert normalize_complexity("high") == "complex"

    def test_maps_medium_to_moderate(self) -> None:
        assert normalize_complexity("medium") == "moderate"

    def test_maps_other_aliases(self) -> None:
        assert normalize_complexity("easy") == "simple"
        assert normalize_complexity("hard") == "complex"
        assert normalize_complexity("difficult") == "complex"
        assert normalize_complexity("intermediate") == "moderate"

    def test_is_case_insensitive(self) -> None:
        assert normalize_complexity("LOW") == "simple"
        assert normalize_complexity("High") == "complex"
        assert normalize_complexity("MODERATE") == "moderate"

    def test_maps_numeric_1_to_3_to_simple(self) -> None:
        assert normalize_complexity(1) == "simple"
        assert normalize_complexity(3) == "simple"

    def test_maps_numeric_4_to_6_to_moderate(self) -> None:
        assert normalize_complexity(4) == "moderate"
        assert normalize_complexity(6) == "moderate"

    def test_maps_numeric_7_to_10_to_complex(self) -> None:
        assert normalize_complexity(7) == "complex"
        assert normalize_complexity(10) == "complex"

    def test_defaults_free_text_to_moderate(self) -> None:
        assert normalize_complexity("detailed") == "moderate"
        assert (
            normalize_complexity("very complex with many deps") == "moderate"
        )

    def test_defaults_none_to_moderate(self) -> None:
        assert normalize_complexity(None) == "moderate"

    def test_defaults_zero_and_negative_numbers_to_moderate(self) -> None:
        assert normalize_complexity(0) == "moderate"
        assert normalize_complexity(-5) == "moderate"


class TestNormalizeBatchOutput:
    """Port of describe('normalizeBatchOutput', ...)."""

    def test_normalizes_ids_and_numeric_complexity_rewrites_edges(self) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "file:src/good.ts",
                        "type": "file",
                        "name": "good.ts",
                        "filePath": "src/good.ts",
                        "summary": "A good file",
                        "tags": ["util"],
                        "complexity": "simple",
                    },
                    {
                        "id": "my-project:file:src/bad.ts",
                        "type": "file",
                        "name": "bad.ts",
                        "filePath": "src/bad.ts",
                        "summary": "Project-prefixed",
                        "tags": ["api"],
                        "complexity": "simple",
                    },
                    {
                        "id": "src/bare.ts",
                        "type": "file",
                        "name": "bare.ts",
                        "filePath": "src/bare.ts",
                        "summary": "Bare path",
                        "tags": [],
                        "complexity": 4,
                    },
                ],
                "edges": [
                    {
                        "source": "file:src/good.ts",
                        "target": "my-project:file:src/bad.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                    {
                        "source": "src/bare.ts",
                        "target": "file:src/good.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        assert len(result.nodes) == 3
        assert result.nodes[0]["id"] == "file:src/good.ts"
        assert result.nodes[1]["id"] == "file:src/bad.ts"
        assert result.nodes[2]["id"] == "file:src/bare.ts"
        # Only numeric complexity is fixed here; string aliases are upstream
        assert result.nodes[2]["complexity"] == "moderate"

        # Edges should be rewritten through the ID map
        assert len(result.edges) == 2
        assert result.edges[0]["source"] == "file:src/good.ts"
        assert result.edges[0]["target"] == "file:src/bad.ts"
        assert result.edges[1]["source"] == "file:src/bare.ts"

        assert result.stats.ids_fixed == 2
        assert result.stats.complexity_fixed == 1  # only the numeric one
        assert result.stats.edges_rewritten == 2
        assert result.stats.dangling_edges_dropped == 0

    def test_drops_dangling_edges_after_normalization(self) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "file:src/a.ts",
                        "type": "file",
                        "name": "a.ts",
                        "summary": "File A",
                        "tags": [],
                        "complexity": "simple",
                    },
                ],
                "edges": [
                    {
                        "source": "file:src/a.ts",
                        "target": "file:src/nonexistent.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        assert len(result.edges) == 0
        assert result.stats.dangling_edges_dropped == 1
        assert len(result.stats.dropped_edges) == 1
        assert result.stats.dropped_edges[0] == {
            "source": "file:src/a.ts",
            "target": "file:src/nonexistent.ts",
            "type": "imports",
            "reason": "missing-target",
        }

    def test_deduplicates_nodes_keeping_last_occurrence(self) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "file:src/a.ts",
                        "type": "file",
                        "name": "a.ts",
                        "summary": "First version",
                        "tags": [],
                        "complexity": "simple",
                    },
                    {
                        "id": "file:src/a.ts",
                        "type": "file",
                        "name": "a.ts",
                        "summary": "Second version",
                        "tags": ["updated"],
                        "complexity": "complex",
                    },
                ],
                "edges": [],
            }
        )

        assert len(result.nodes) == 1
        assert result.nodes[0]["summary"] == "Second version"

    def test_deduplicates_edges_after_id_rewriting(self) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "file:src/a.ts",
                        "type": "file",
                        "name": "a.ts",
                        "summary": "A",
                        "tags": [],
                        "complexity": "simple",
                    },
                    {
                        "id": "file:src/b.ts",
                        "type": "file",
                        "name": "b.ts",
                        "summary": "B",
                        "tags": [],
                        "complexity": "simple",
                    },
                ],
                "edges": [
                    {
                        "source": "file:src/a.ts",
                        "target": "file:src/b.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                    {
                        "source": "proj:file:src/a.ts",
                        "target": "file:src/b.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        # Both edges resolve to the same source after normalization — deduplicated
        assert len(result.edges) == 1

    def test_returns_accurate_stats(self) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "file:src/ok.ts",
                        "type": "file",
                        "name": "ok.ts",
                        "summary": "OK",
                        "tags": [],
                        "complexity": "simple",
                    },
                    {
                        "id": "proj:file:src/fix.ts",
                        "type": "file",
                        "name": "fix.ts",
                        "summary": "Needs fix",
                        "tags": [],
                        "complexity": 2,
                    },
                ],
                "edges": [
                    {
                        "source": "proj:file:src/fix.ts",
                        "target": "file:src/ok.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                    {
                        "source": "file:src/ok.ts",
                        "target": "file:src/gone.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        assert result.stats.ids_fixed == 1
        assert result.stats.complexity_fixed == 1
        assert result.stats.edges_rewritten == 1
        assert result.stats.dangling_edges_dropped == 1
        assert len(result.edges) == 1

    def test_resolves_edge_endpoints_with_different_malformed_variants_than_node_ids(
        self,
    ) -> None:
        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "src/bare.ts",
                        "type": "file",
                        "name": "bare.ts",
                        "filePath": "src/bare.ts",
                        "summary": "Bare",
                        "tags": [],
                        "complexity": "simple",
                    },
                    {
                        "id": "file:src/target.ts",
                        "type": "file",
                        "name": "target.ts",
                        "filePath": "src/target.ts",
                        "summary": "Target",
                        "tags": [],
                        "complexity": "simple",
                    },
                ],
                "edges": [
                    {
                        "source": "my-project:file:src/bare.ts",
                        "target": "file:src/target.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        assert len(result.edges) == 1
        assert result.edges[0]["source"] == "file:src/bare.ts"
        assert result.edges[0]["target"] == "file:src/target.ts"


class TestNormalizeBatchOutputIntegration:
    """Port of describe('normalizeBatchOutput integration', ...)."""

    def test_produces_output_that_passes_validate_graph_after_wrapping(
        self,
    ) -> None:
        from datetime import datetime, timezone

        result = normalize_batch_output(
            {
                "nodes": [
                    {
                        "id": "my-project:file:src/index.ts",
                        "type": "file",
                        "name": "index.ts",
                        "filePath": "src/index.ts",
                        "summary": "Entry point",
                        "tags": ["entry"],
                        "complexity": 3,
                    },
                    {
                        "id": "src/utils.ts",
                        "type": "file",
                        "name": "utils.ts",
                        "filePath": "src/utils.ts",
                        "summary": "Utilities",
                        "tags": [],
                        "complexity": "simple",
                    },
                ],
                "edges": [
                    {
                        "source": "my-project:file:src/index.ts",
                        "target": "src/utils.ts",
                        "type": "imports",
                        "direction": "forward",
                        "weight": 0.7,
                    },
                ],
            }
        )

        graph: dict[str, object] = {
            "version": "1.0.0",
            "project": {
                "name": "test",
                "languages": ["typescript"],
                "frameworks": [],
                "description": "Test project",
                "analyzedAt": datetime.now(timezone.utc).isoformat(),
                "gitCommitHash": "abc123",
            },
            "nodes": result.nodes,
            "edges": result.edges,
            "layers": [],
            "tour": [],
        }

        validation = validate_graph(graph)
        assert validation.success is True
        assert validation.data is not None
        assert len(validation.data["nodes"]) == 2
        assert len(validation.data["edges"]) == 1
