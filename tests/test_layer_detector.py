"""Tests for analysis/layer_detector.py — port of layer-detector.test.ts."""

from __future__ import annotations

import json

from understand_anything.analysis.layer_detector import (
    apply_llm_layers,
    build_layer_detection_prompt,
    detect_layers,
    parse_layer_detection_response,
)
from understand_anything.types import GraphNode, KnowledgeGraph, ProjectMeta


def _make_node(
    overrides: dict | None = None,
) -> GraphNode:
    defaults: dict = {
        "id": "f1",
        "type": "file",
        "name": "index.ts",
        "summary": "",
        "tags": [],
        "complexity": "simple",
    }
    merged = {**defaults, **(overrides or {})}
    # Set filePath separately since it's None by default and aliased
    file_path = merged.pop("filePath", None)
    node = GraphNode(**merged)
    if file_path is not None:
        node.file_path = file_path
    return node


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


class TestDetectLayers:
    """Port of describe('detectLayers', ...)."""

    def test_detects_api_layer_from_routes_controllers_handlers_endpoints(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "users.ts", "filePath": "src/routes/users.ts"}),
                _make_node({"id": "f2", "name": "auth.ts", "filePath": "src/controllers/auth.ts"}),
                _make_node({"id": "f3", "name": "error.ts", "filePath": "src/handlers/error.ts"}),
                _make_node({"id": "f4", "name": "health.ts", "filePath": "src/api/health.ts"}),
                _make_node({"id": "f5", "name": "users.ts", "filePath": "src/endpoints/users.ts"}),
            ],
        })
        layers = detect_layers(graph)
        api_layer = next((ly for ly in layers if ly.name == "API Layer"), None)
        assert api_layer is not None
        assert "f1" in api_layer.node_ids
        assert "f2" in api_layer.node_ids
        assert "f3" in api_layer.node_ids
        assert "f4" in api_layer.node_ids
        assert "f5" in api_layer.node_ids

    def test_detects_ui_layer_from_components_views_pages_widgets_paths(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "Button.tsx", "filePath": "src/components/Button.tsx"}),
                _make_node({"id": "f2", "name": "Home.tsx", "filePath": "src/views/Home.tsx"}),
                _make_node({"id": "f3", "name": "Login.tsx", "filePath": "src/pages/Login.tsx"}),
            ],
        })
        layers = detect_layers(graph)
        ui_layer = next((ly for ly in layers if ly.name == "UI Layer"), None)
        assert ui_layer is not None
        assert "f1" in ui_layer.node_ids
        assert "f2" in ui_layer.node_ids
        assert "f3" in ui_layer.node_ids

    def test_detects_service_layer_from_services_usecases_business_paths(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "auth.ts", "filePath": "src/services/auth.ts"}),
                _make_node({"id": "f2", "name": "createUser.ts", "filePath": "src/usecases/createUser.ts"}),
                _make_node({"id": "f3", "name": "rules.ts", "filePath": "src/business/rules.ts"}),
            ],
        })
        layers = detect_layers(graph)
        service_layer = next((ly for ly in layers if ly.name == "Service Layer"), None)
        assert service_layer is not None
        assert "f1" in service_layer.node_ids
        assert "f2" in service_layer.node_ids
        assert "f3" in service_layer.node_ids

    def test_detects_data_layer_from_model_entity_repository_paths(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "User.ts", "filePath": "src/models/User.ts"}),
                _make_node({"id": "f2", "name": "Post.ts", "filePath": "src/entity/Post.ts"}),
                _make_node({"id": "f3", "name": "UserRepo.ts", "filePath": "src/repository/UserRepo.ts"}),
            ],
        })
        layers = detect_layers(graph)
        data_layer = next((ly for ly in layers if ly.name == "Data Layer"), None)
        assert data_layer is not None
        assert "f1" in data_layer.node_ids
        assert "f2" in data_layer.node_ids
        assert "f3" in data_layer.node_ids

    def test_puts_unmatched_file_nodes_in_core_layer(self) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "main.ts", "filePath": "src/main.ts"}),
                _make_node({"id": "f2", "name": "app.ts", "filePath": "src/app.ts"}),
            ],
        })
        layers = detect_layers(graph)
        core_layer = next((ly for ly in layers if ly.name == "Core"), None)
        assert core_layer is not None
        assert "f1" in core_layer.node_ids
        assert "f2" in core_layer.node_ids

    def test_assigns_unique_kebab_case_ids_to_each_layer(self) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "users.ts", "filePath": "src/routes/users.ts"}),
                _make_node({"id": "f2", "name": "User.ts", "filePath": "src/models/User.ts"}),
                _make_node({"id": "f3", "name": "main.ts", "filePath": "src/main.ts"}),
            ],
        })
        layers = detect_layers(graph)
        ids = [ly.id for ly in layers]
        for lid in ids:
            assert lid.startswith("layer:")
        assert len(set(ids)) == len(ids)

    def test_only_assigns_file_type_nodes_ignoring_functions_and_classes(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "users.ts", "type": "file", "filePath": "src/routes/users.ts"}),
                _make_node({"id": "fn1", "name": "getUser", "type": "function", "filePath": "src/routes/users.ts"}),
                _make_node({"id": "c1", "name": "UserController", "type": "class", "filePath": "src/routes/users.ts"}),
            ],
        })
        layers = detect_layers(graph)
        all_node_ids = []
        for ly in layers:
            all_node_ids.extend(ly.node_ids)
        assert "f1" in all_node_ids
        assert "fn1" not in all_node_ids
        assert "c1" not in all_node_ids


class TestBuildLayerDetectionPrompt:
    """Port of describe('buildLayerDetectionPrompt', ...)."""

    def test_contains_file_paths_and_mentions_json_in_the_prompt(self) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "index.ts", "filePath": "src/index.ts"}),
                _make_node({"id": "f2", "name": "app.ts", "filePath": "src/app.ts"}),
            ],
        })
        prompt = build_layer_detection_prompt(graph)
        assert "src/index.ts" in prompt
        assert "src/app.ts" in prompt
        assert "JSON" in prompt


class TestParseLayerDetectionResponse:
    """Port of describe('parseLayerDetectionResponse', ...)."""

    def test_parses_valid_json_response(self) -> None:
        response = json.dumps([
            {
                "name": "API",
                "description": "Handles HTTP requests",
                "filePatterns": ["src/routes/", "src/controllers/"],
            },
            {
                "name": "Data",
                "description": "Database models and queries",
                "filePatterns": ["src/models/"],
            },
        ])
        result = parse_layer_detection_response(response)
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "API"
        assert result[0]["filePatterns"] == ["src/routes/", "src/controllers/"]

    def test_parses_json_wrapped_in_markdown_fences(self) -> None:
        response = (
            "Here are the layers:\n"
            "```json\n"
            '[\n  { "name": "UI", "description": "Frontend components",'
            ' "filePatterns": ["src/components/"] }\n'
            "]\n"
            "```"
        )
        result = parse_layer_detection_response(response)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "UI"

    def test_returns_none_for_invalid_unparseable_input(self) -> None:
        assert parse_layer_detection_response("not json at all") is None
        assert parse_layer_detection_response("{}") is None
        assert parse_layer_detection_response("") is None


class TestApplyLLMLayers:
    """Port of describe('applyLLMLayers', ...)."""

    def test_assigns_file_nodes_to_llm_provided_layers_and_puts_unmatched_in_other(
        self,
    ) -> None:
        graph = _make_graph({
            "nodes": [
                _make_node({"id": "f1", "name": "users.ts", "filePath": "src/routes/users.ts"}),
                _make_node({"id": "f2", "name": "User.ts", "filePath": "src/models/User.ts"}),
                _make_node({"id": "f3", "name": "main.ts", "filePath": "src/main.ts"}),
            ],
        })
        llm_layers = [
            {"name": "API", "description": "HTTP endpoints", "filePatterns": ["src/routes/"]},
            {"name": "Data", "description": "Models", "filePatterns": ["src/models/"]},
        ]
        layers = apply_llm_layers(graph, llm_layers)

        api_layer = next((ly for ly in layers if ly.name == "API"), None)
        assert api_layer is not None
        assert "f1" in api_layer.node_ids

        data_layer = next((ly for ly in layers if ly.name == "Data"), None)
        assert data_layer is not None
        assert "f2" in data_layer.node_ids

        other_layer = next((ly for ly in layers if ly.name == "Other"), None)
        assert other_layer is not None
        assert "f3" in other_layer.node_ids
