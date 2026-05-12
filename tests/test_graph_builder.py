"""Tests for analysis/graph_builder.py — port of graph-builder.test.ts."""

from __future__ import annotations

import pytest

from understand_anything.analysis.graph_builder import GraphBuilder
from understand_anything.types import (
    ClassInfo,
    DefinitionInfo,
    EndpointInfo,
    FunctionInfo,
    ResourceInfo,
    ServiceInfo,
    StepInfo,
    StructuralAnalysis,
)


class TestGraphBuilder:
    """Core GraphBuilder tests — port of describe('GraphBuilder', ...)."""

    def test_should_create_file_nodes_from_file_list(self) -> None:
        builder = GraphBuilder("test-project", "abc123")

        builder.add_file(
            "src/index.ts",
            summary="Entry point",
            tags=["entry"],
            complexity="simple",
        )
        builder.add_file(
            "src/utils.ts",
            summary="Utility functions",
            tags=["utility"],
            complexity="moderate",
        )

        graph = builder.build()

        assert len(graph.nodes) == 2
        assert graph.nodes[0].id == "file:src/index.ts"
        assert graph.nodes[0].type == "file"
        assert graph.nodes[0].name == "index.ts"
        assert graph.nodes[0].file_path == "src/index.ts"
        assert graph.nodes[0].summary == "Entry point"
        assert graph.nodes[0].tags == ["entry"]
        assert graph.nodes[0].complexity == "simple"

        assert graph.nodes[1].id == "file:src/utils.ts"
        assert graph.nodes[1].type == "file"
        assert graph.nodes[1].name == "utils.ts"
        assert graph.nodes[1].file_path == "src/utils.ts"
        assert graph.nodes[1].summary == "Utility functions"

    def test_should_create_function_and_class_nodes_from_structural_analysis(
        self,
    ) -> None:
        builder = GraphBuilder("test-project", "abc123")
        analysis = StructuralAnalysis(
            functions=[
                FunctionInfo(
                    name="processData",
                    line_range=(10, 25),
                    params=["input"],
                    return_type="string",
                ),
                FunctionInfo(
                    name="validate", line_range=(30, 40), params=["data"]
                ),
            ],
            classes=[
                ClassInfo(
                    name="DataStore",
                    line_range=(50, 100),
                    methods=["get", "set"],
                    properties=["data"],
                ),
            ],
        )

        builder.add_file_with_analysis(
            "src/service.ts",
            analysis,
            summary="Service module",
            tags=["service"],
            complexity="complex",
            file_summary="Handles data processing",
            summaries={
                "processData": "Processes raw input data",
                "validate": "Validates data format",
                "DataStore": "Manages stored data",
            },
        )

        graph = builder.build()

        # 1 file + 2 functions + 1 class = 4 nodes
        assert len(graph.nodes) == 4

        file_node = next(n for n in graph.nodes if n.id == "file:src/service.ts")
        assert file_node.type == "file"
        assert file_node.summary == "Handles data processing"

        func_node = next(
            n for n in graph.nodes if n.id == "function:src/service.ts:processData"
        )
        assert func_node.type == "function"
        assert func_node.name == "processData"
        assert func_node.line_range == (10, 25)
        assert func_node.summary == "Processes raw input data"

        validate_node = next(
            n for n in graph.nodes if n.id == "function:src/service.ts:validate"
        )
        assert validate_node.summary == "Validates data format"

        class_node = next(
            n for n in graph.nodes if n.id == "class:src/service.ts:DataStore"
        )
        assert class_node.type == "class"
        assert class_node.name == "DataStore"
        assert class_node.summary == "Manages stored data"

    def test_should_create_contains_edges_between_files_and_their_functions_classes(
        self,
    ) -> None:
        builder = GraphBuilder("test-project", "abc123")
        analysis = StructuralAnalysis(
            functions=[
                FunctionInfo(name="helper", line_range=(5, 15), params=[]),
            ],
            classes=[
                ClassInfo(
                    name="Widget",
                    line_range=(20, 50),
                    methods=[],
                    properties=[],
                ),
            ],
        )

        builder.add_file_with_analysis(
            "src/widget.ts",
            analysis,
            summary="Widget module",
            tags=[],
            complexity="moderate",
            file_summary="Widget component",
            summaries={"helper": "Helper function", "Widget": "Widget class"},
        )

        graph = builder.build()

        contains_edges = [e for e in graph.edges if e.type == "contains"]
        assert len(contains_edges) == 2

        assert contains_edges[0].source == "file:src/widget.ts"
        assert contains_edges[0].target == "function:src/widget.ts:helper"
        assert contains_edges[0].type == "contains"
        assert contains_edges[0].direction == "forward"
        assert contains_edges[0].weight == 1

        assert contains_edges[1].source == "file:src/widget.ts"
        assert contains_edges[1].target == "class:src/widget.ts:Widget"
        assert contains_edges[1].type == "contains"
        assert contains_edges[1].direction == "forward"
        assert contains_edges[1].weight == 1

    def test_should_create_import_edges_between_files(self) -> None:
        builder = GraphBuilder("test-project", "abc123")

        builder.add_file(
            "src/index.ts", summary="Entry", tags=[], complexity="simple"
        )
        builder.add_file(
            "src/utils.ts", summary="Utils", tags=[], complexity="simple"
        )

        builder.add_import_edge("src/index.ts", "src/utils.ts")

        graph = builder.build()
        import_edges = [e for e in graph.edges if e.type == "imports"]
        assert len(import_edges) == 1
        assert import_edges[0].source == "file:src/index.ts"
        assert import_edges[0].target == "file:src/utils.ts"
        assert import_edges[0].type == "imports"
        assert import_edges[0].direction == "forward"

    def test_should_create_call_edges_between_functions(self) -> None:
        builder = GraphBuilder("test-project", "abc123")

        builder.add_call_edge("src/index.ts", "main", "src/utils.ts", "helper")

        graph = builder.build()
        call_edges = [e for e in graph.edges if e.type == "calls"]
        assert len(call_edges) == 1
        assert call_edges[0].source == "function:src/index.ts:main"
        assert call_edges[0].target == "function:src/utils.ts:helper"
        assert call_edges[0].type == "calls"
        assert call_edges[0].direction == "forward"

    def test_should_set_project_metadata_correctly(self) -> None:
        builder = GraphBuilder("my-awesome-project", "deadbeef")

        builder.add_file(
            "src/app.ts", summary="App", tags=[], complexity="simple"
        )
        builder.add_file(
            "src/script.py", summary="Script", tags=[], complexity="simple"
        )

        graph = builder.build()

        assert graph.version == "1.0.0"
        assert graph.project.name == "my-awesome-project"
        assert graph.project.git_commit_hash == "deadbeef"
        assert sorted(graph.project.languages) == ["python", "typescript"]
        assert graph.project.analyzed_at
        assert graph.layers == []
        assert graph.tour == []

    def test_should_detect_languages_from_file_extensions(self) -> None:
        builder = GraphBuilder("polyglot", "hash123")

        builder.add_file("main.go", summary="", tags=[], complexity="simple")
        builder.add_file("lib.rs", summary="", tags=[], complexity="simple")
        builder.add_file("app.js", summary="", tags=[], complexity="simple")

        graph = builder.build()
        assert sorted(graph.project.languages) == ["go", "javascript", "rust"]


class TestNonCodeFileSupport:
    """Non-code file tests — port of describe('Non-code file support', ...)."""

    def test_adds_non_code_file_nodes_with_correct_types_and_node_type_prefixed_id(
        self,
    ) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file(
            "README.md",
            node_type="document",
            summary="Project documentation",
            tags=["documentation"],
            complexity="simple",
        )
        graph = builder.build()
        assert len(graph.nodes) == 1
        assert graph.nodes[0].type == "document"
        assert graph.nodes[0].id == "document:README.md"

    def test_adds_non_code_child_nodes_definitions(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "schema.sql",
            node_type="file",
            summary="Database schema",
            tags=["database"],
            complexity="moderate",
            definitions=[
                DefinitionInfo(
                    name="users",
                    kind="table",
                    line_range=(1, 20),
                    fields=["id", "name", "email"],
                ),
            ],
        )
        graph = builder.build()
        # File node + table child node
        assert len(graph.nodes) == 2
        assert graph.nodes[1].type == "table"
        assert graph.nodes[1].name == "users"
        # Contains edge
        assert any(
            e.type == "contains" and "users" in e.target for e in graph.edges
        )

    def test_adds_service_child_nodes(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "docker-compose.yml",
            node_type="config",
            summary="Docker compose config",
            tags=["infra"],
            complexity="moderate",
            services=[
                ServiceInfo(name="web", image="node:22", ports=[3000]),
                ServiceInfo(name="db", image="postgres:15", ports=[5432]),
            ],
        )
        graph = builder.build()
        # File node + 2 service child nodes
        assert len(graph.nodes) == 3
        assert graph.nodes[1].type == "service"
        assert graph.nodes[1].name == "web"
        assert graph.nodes[2].type == "service"
        assert graph.nodes[2].name == "db"

    def test_adds_endpoint_child_nodes(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "schema.graphql",
            node_type="schema",
            summary="GraphQL schema",
            tags=["api"],
            complexity="moderate",
            endpoints=[
                EndpointInfo(method="Query", path="users", line_range=(5, 5)),
            ],
        )
        graph = builder.build()
        assert len(graph.nodes) == 2
        assert graph.nodes[1].type == "endpoint"

    def test_adds_resource_child_nodes(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "main.tf",
            node_type="resource",
            summary="Terraform config",
            tags=["infra"],
            complexity="moderate",
            resources=[
                ResourceInfo(
                    name="aws_s3_bucket.main",
                    kind="aws_s3_bucket",
                    line_range=(1, 10),
                ),
            ],
        )
        graph = builder.build()
        assert len(graph.nodes) == 2
        assert graph.nodes[1].type == "resource"
        assert graph.nodes[1].name == "aws_s3_bucket.main"

    def test_adds_step_child_nodes(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "Makefile",
            node_type="pipeline",
            summary="Build targets",
            tags=["build"],
            complexity="simple",
            steps=[
                StepInfo(name="build", line_range=(1, 3)),
                StepInfo(name="test", line_range=(5, 7)),
            ],
        )
        graph = builder.build()
        assert len(graph.nodes) == 3
        assert graph.nodes[1].type == "pipeline"
        assert graph.nodes[1].name == "build"

    def test_detects_non_code_languages_from_extension_map(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_file(
            "config.yaml", summary="Config", tags=[], complexity="simple"
        )
        graph = builder.build()
        assert "yaml" in graph.project.languages

    def test_detects_new_non_code_extensions(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_file(
            "schema.graphql", summary="Schema", tags=[], complexity="simple"
        )
        builder.add_file(
            "main.tf", summary="Terraform", tags=[], complexity="simple"
        )
        builder.add_file(
            "types.proto", summary="Protobuf", tags=[], complexity="simple"
        )
        graph = builder.build()
        assert "graphql" in graph.project.languages
        assert "terraform" in graph.project.languages
        assert "protobuf" in graph.project.languages

    def test_map_kind_to_node_type_falls_back_to_concept_for_unknown_kinds(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import logging

        logger = logging.getLogger("understand_anything.analysis.graph_builder")
        logger.setLevel(logging.WARNING)

        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "schema.sql",
            node_type="file",
            summary="Schema",
            tags=[],
            complexity="simple",
            definitions=[
                DefinitionInfo(
                    name="doStuff",
                    kind="procedure",
                    line_range=(1, 10),
                    fields=[],
                ),
            ],
        )
        graph = builder.build()
        child_node = next(n for n in graph.nodes if n.name == "doStuff")
        assert child_node is not None
        assert child_node.type == "concept"

    def test_skips_duplicate_node_ids_in_add_non_code_file_with_analysis(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import logging

        logger = logging.getLogger("understand_anything.analysis.graph_builder")
        logger.setLevel(logging.WARNING)

        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "schema.sql",
            node_type="file",
            summary="Schema",
            tags=[],
            complexity="simple",
            definitions=[
                DefinitionInfo(
                    name="users",
                    kind="table",
                    line_range=(1, 10),
                    fields=["id"],
                ),
                DefinitionInfo(
                    name="users",
                    kind="table",
                    line_range=(12, 20),
                    fields=["id", "name"],
                ),
            ],
        )
        graph = builder.build()
        # Only the file node + one table node (duplicate skipped)
        table_nodes = [n for n in graph.nodes if n.name == "users"]
        assert len(table_nodes) == 1

    def test_uses_node_type_in_file_id_for_contains_edges(self) -> None:
        builder = GraphBuilder("test", "abc123")
        builder.add_non_code_file_with_analysis(
            "docker-compose.yml",
            node_type="config",
            summary="Docker compose config",
            tags=[],
            complexity="simple",
            services=[
                ServiceInfo(name="web", ports=[3000]),
            ],
        )
        graph = builder.build()
        contains_edge = next(e for e in graph.edges if e.type == "contains")
        assert contains_edge is not None
        assert contains_edge.source == "config:docker-compose.yml"
        assert contains_edge.target == "service:docker-compose.yml:web"
