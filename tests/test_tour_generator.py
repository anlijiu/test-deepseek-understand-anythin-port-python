"""Tests for analysis/tour_generator.py — port of tour-generator.test.ts."""

from __future__ import annotations

import json

from understand_anything.analysis.tour_generator import (
    build_tour_generation_prompt,
    generate_heuristic_tour,
    parse_tour_generation_response,
)
from understand_anything.types import (
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    Layer,
    ProjectMeta,
)


def _sample_graph() -> KnowledgeGraph:
    return KnowledgeGraph(
        version="1.0.0",
        project=ProjectMeta(
            name="test-project",
            languages=["typescript"],
            frameworks=["express"],
            description="A test project",
            analyzedAt="2026-03-14T00:00:00Z",
            gitCommitHash="abc123",
        ),
        nodes=[
            GraphNode(id="file:src/index.ts", type="file", name="index.ts", filePath="src/index.ts", summary="Application entry point", tags=["entry", "server"], complexity="simple"),
            GraphNode(id="file:src/routes.ts", type="file", name="routes.ts", filePath="src/routes.ts", summary="Route definitions", tags=["routes", "api"], complexity="moderate"),
            GraphNode(id="file:src/service.ts", type="file", name="service.ts", filePath="src/service.ts", summary="Business logic", tags=["service"], complexity="complex"),
            GraphNode(id="file:src/db.ts", type="file", name="db.ts", filePath="src/db.ts", summary="Database connection", tags=["database"], complexity="simple"),
            GraphNode(id="concept:auth-flow", type="concept", name="Auth Flow", summary="Authentication concept", tags=["concept", "auth"], complexity="moderate"),
        ],
        edges=[
            GraphEdge(source="file:src/index.ts", target="file:src/routes.ts", type="imports", direction="forward", weight=0.9),
            GraphEdge(source="file:src/routes.ts", target="file:src/service.ts", type="calls", direction="forward", weight=0.8),
            GraphEdge(source="file:src/service.ts", target="file:src/db.ts", type="reads_from", direction="forward", weight=0.7),
        ],
        layers=[
            Layer(id="layer:api", name="API Layer", description="HTTP routes", nodeIds=["file:src/index.ts", "file:src/routes.ts"]),
            Layer(id="layer:service", name="Service Layer", description="Business logic", nodeIds=["file:src/service.ts"]),
            Layer(id="layer:data", name="Data Layer", description="Database", nodeIds=["file:src/db.ts"]),
        ],
        tour=[],
    )


class TestBuildTourGenerationPrompt:
    """Port of describe('buildTourGenerationPrompt', ...)."""

    def test_includes_project_name_and_description(self) -> None:
        prompt = build_tour_generation_prompt(_sample_graph())
        assert "test-project" in prompt
        assert "A test project" in prompt

    def test_includes_all_node_summaries(self) -> None:
        prompt = build_tour_generation_prompt(_sample_graph())
        assert "Application entry point" in prompt
        assert "Route definitions" in prompt
        assert "Business logic" in prompt
        assert "Database connection" in prompt
        assert "Authentication concept" in prompt

    def test_includes_layer_information(self) -> None:
        prompt = build_tour_generation_prompt(_sample_graph())
        assert "API Layer" in prompt
        assert "Service Layer" in prompt
        assert "Data Layer" in prompt

    def test_requests_json_output_format(self) -> None:
        prompt = build_tour_generation_prompt(_sample_graph())
        assert "JSON" in prompt
        assert "steps" in prompt


class TestParseTourGenerationResponse:
    """Port of describe('parseTourGenerationResponse', ...)."""

    def test_parses_valid_json_response_with_tour_steps(self) -> None:
        response = json.dumps({
            "steps": [
                {
                    "order": 1,
                    "title": "Entry Point",
                    "description": "Start here",
                    "nodeIds": ["file:src/index.ts"],
                },
                {
                    "order": 2,
                    "title": "Routes",
                    "description": "API routes",
                    "nodeIds": ["file:src/routes.ts"],
                },
            ],
        })
        steps = parse_tour_generation_response(response)
        assert len(steps) == 2
        assert steps[0].order == 1
        assert steps[0].title == "Entry Point"
        assert steps[0].node_ids == ["file:src/index.ts"]
        assert steps[1].order == 2

    def test_extracts_json_from_markdown_code_blocks(self) -> None:
        response = (
            "Here is the tour:\n"
            "```json\n"
            "{\n"
            '  "steps": [\n'
            "    {\n"
            '      "order": 1,\n'
            '      "title": "Start",\n'
            '      "description": "The beginning",\n'
            '      "nodeIds": ["file:src/index.ts"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```"
        )
        steps = parse_tour_generation_response(response)
        assert len(steps) == 1
        assert steps[0].title == "Start"

    def test_returns_empty_array_for_unparseable_response(self) -> None:
        assert parse_tour_generation_response("not json at all") == []
        assert parse_tour_generation_response("") == []
        assert parse_tour_generation_response("random text here") == []

    def test_filters_out_steps_with_missing_required_fields(self) -> None:
        response = json.dumps({
            "steps": [
                {
                    "order": 1,
                    "title": "Valid Step",
                    "description": "Has everything",
                    "nodeIds": ["file:src/index.ts"],
                },
                {
                    "order": 2,
                    "description": "Missing title",
                    "nodeIds": ["file:src/routes.ts"],
                },
                {
                    "order": 3,
                    "title": "Missing description",
                    "nodeIds": ["file:src/routes.ts"],
                },
                {
                    "order": 4,
                    "title": "Missing nodeIds",
                    "description": "No nodes",
                },
                {
                    "title": "Missing order",
                    "description": "No order",
                    "nodeIds": ["file:src/db.ts"],
                },
            ],
        })
        steps = parse_tour_generation_response(response)
        assert len(steps) == 1
        assert steps[0].title == "Valid Step"


class TestGenerateHeuristicTour:
    """Port of describe('generateHeuristicTour', ...)."""

    def test_starts_with_entry_point_nodes(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        first_step_node_ids = tour[0].node_ids
        assert "file:src/index.ts" in first_step_node_ids

    def test_follows_topological_order(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        code_steps = [
            s for s in tour
            if "concept" not in s.title.lower()
        ]
        ordered_node_ids = []
        for s in code_steps:
            ordered_node_ids.extend(s.node_ids)

        index_pos = ordered_node_ids.index("file:src/index.ts")
        routes_pos = ordered_node_ids.index("file:src/routes.ts")
        service_pos = ordered_node_ids.index("file:src/service.ts")
        db_pos = ordered_node_ids.index("file:src/db.ts")

        assert index_pos < routes_pos
        assert routes_pos < service_pos
        assert service_pos < db_pos

    def test_includes_concept_nodes_in_separate_steps(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        concept_step = next(
            (s for s in tour if "concept:auth-flow" in s.node_ids),
            None,
        )
        assert concept_step is not None
        file_node_ids = {
            n.id for n in _sample_graph().nodes if n.type == "file"
        }
        for file_id in file_node_ids:
            assert file_id not in concept_step.node_ids

    def test_assigns_order_numbers_sequentially(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        for i, step in enumerate(tour):
            assert step.order == i + 1

    def test_groups_nodes_by_layer_when_layers_exist(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        step_titles = [s.title for s in tour]
        assert any("API Layer" in t for t in step_titles)
        assert any("Service Layer" in t for t in step_titles)
        assert any("Data Layer" in t for t in step_titles)

    def test_produces_valid_tour_step_objects(self) -> None:
        tour = generate_heuristic_tour(_sample_graph())
        for step in tour:
            assert isinstance(step.order, int)
            assert isinstance(step.title, str)
            assert len(step.title) > 0
            assert isinstance(step.description, str)
            assert len(step.description) > 0
            assert isinstance(step.node_ids, list)
            assert len(step.node_ids) > 0

    def test_handles_graph_with_no_edges_gracefully(self) -> None:
        graph = _sample_graph()
        no_edges_graph = KnowledgeGraph(
            **{**graph.model_dump(), "edges": [], "layers": []}
        )
        tour = generate_heuristic_tour(no_edges_graph)
        assert len(tour) > 0
        all_node_ids = []
        for s in tour:
            all_node_ids.extend(s.node_ids)
        for node in no_edges_graph.nodes:
            assert node.id in all_node_ids

    def test_handles_graph_with_no_layers(self) -> None:
        graph = _sample_graph()
        no_layers_graph = KnowledgeGraph(
            **{**graph.model_dump(), "layers": []}
        )
        tour = generate_heuristic_tour(no_layers_graph)
        assert len(tour) > 0
        code_steps = [
            s for s in tour
            if "concept" not in s.title.lower()
        ]
        # With 4 code nodes and batches of 3, expect 2 code steps
        assert len(code_steps) == 2
