"""Tests for analysis/language_lesson.py — port of language-lesson.test.ts."""

from __future__ import annotations

import json

from understand_anything.analysis.language_lesson import (
    build_language_lesson_prompt,
    detect_language_concepts,
    get_language_display_name,
    parse_language_lesson_response,
)
from understand_anything.types import GraphEdge, GraphNode


def _make_node(overrides: dict | None = None) -> GraphNode:
    defaults: dict = {
        "id": "func:src/app.ts:handleRequest",
        "type": "function",
        "name": "handleRequest",
        "summary": "Handles incoming HTTP requests asynchronously",
        "tags": ["async", "api"],
        "complexity": "moderate",
        "filePath": "src/app.ts",
    }
    merged = {**defaults, **(overrides or {})}
    node: GraphNode = GraphNode(**merged)
    if "languageNotes" in (overrides or {}):
        node.language_notes = (overrides or {})["languageNotes"]
    return node


class TestDetectLanguageConcepts:
    """Port of describe('detectLanguageConcepts', ...)."""

    def test_detects_async_await_from_tags(self) -> None:
        node = _make_node({"tags": ["async", "api"]})
        concepts = detect_language_concepts(node, "typescript")
        assert "async/await" in concepts

    def test_detects_dependency_injection_from_summary(self) -> None:
        node = _make_node({"summary": "Uses dependency injection container", "tags": []})
        concepts = detect_language_concepts(node, "typescript")
        assert "dependency injection" in concepts

    def test_detects_decorators_from_language_notes(self) -> None:
        node = _make_node({"languageNotes": "Uses @ decorators extensively"})
        concepts = detect_language_concepts(node, "python")
        assert "decorators" in concepts

    def test_returns_empty_when_no_concepts_match(self) -> None:
        node = _make_node({
            "tags": [],
            "summary": "A simple utility function",
            "languageNotes": "",
        })
        concepts = detect_language_concepts(node, "typescript")
        assert concepts == []

    def test_merges_base_and_language_specific_concepts(self) -> None:
        node = _make_node({
            "tags": ["goroutine", "channel"],
            "summary": "Concurrent worker pool",
        })
        # goroutine/channel keywords match "concurrency" base concept
        concepts = detect_language_concepts(node, "go")
        assert "concurrency" in concepts


class TestGetLanguageDisplayName:
    """Port of describe('getLanguageDisplayName', ...)."""

    def test_uses_language_config_display_name_when_provided(self) -> None:
        lang_config = {"id": "ts", "displayName": "TypeScript", "concepts": []}
        name = get_language_display_name("typescript", lang_config)
        assert name == "TypeScript"

    def test_falls_back_to_capitalization_when_no_config(self) -> None:
        name = get_language_display_name("python", None)
        assert name == "Python"

    def test_falls_back_to_capitalization_when_no_display_name(self) -> None:
        lang_config = {"id": "rs", "concepts": []}
        name = get_language_display_name("rust", lang_config)
        assert name == "Rust"


class TestBuildLanguageLessonPrompt:
    """Port of describe('buildLanguageLessonPrompt', ...)."""

    def test_includes_node_info(self) -> None:
        node = _make_node()
        prompt = build_language_lesson_prompt(node, [], "typescript")
        assert "handleRequest" in prompt
        assert "function" in prompt
        assert "Handles incoming HTTP requests asynchronously" in prompt

    def test_includes_node_info_simple(self) -> None:
        node = _make_node({
            "name": "processData",
            "summary": "Data processing function",
            "type": "function",
            "filePath": "src/utils.ts",
            "tags": ["utility"],
        })
        prompt = build_language_lesson_prompt(node, [], "typescript")
        assert "processData" in prompt
        assert "Data processing function" in prompt
        assert "src/utils.ts" in prompt

    def test_includes_relationship_info(self) -> None:
        node = _make_node({"id": "func:src/app.ts:handleRequest"})
        edges = [
            GraphEdge(source="func:src/app.ts:handleRequest", target="func:src/db.ts:query", type="calls", direction="forward", weight=0.8),
            GraphEdge(source="func:src/router.ts:route", target="func:src/app.ts:handleRequest", type="calls", direction="forward", weight=0.7),
        ]
        prompt = build_language_lesson_prompt(node, edges, "typescript")
        assert "calls" in prompt
        assert "query" in prompt

    def test_includes_detected_concepts(self) -> None:
        node = _make_node({"tags": ["async", "middleware"]})
        prompt = build_language_lesson_prompt(node, [], "typescript")
        assert "async/await" in prompt
        assert "middleware pattern" in prompt

    def test_falls_back_when_no_concepts_detected(self) -> None:
        node = _make_node({"tags": [], "summary": "", "languageNotes": ""})
        prompt = build_language_lesson_prompt(node, [], "go")
        assert "No specific concepts were pre-detected" in prompt
        assert "Go" in prompt


class TestParseLanguageLessonResponse:
    """Port of describe('parseLanguageLessonResponse', ...)."""

    def test_parses_valid_json_response(self) -> None:
        response = json.dumps({
            "languageNotes": "Uses async/await for concurrent operations",
            "concepts": [
                {"name": "async/await", "explanation": "Non-blocking I/O pattern"},
                {"name": "generics", "explanation": "Type parameterization"},
            ],
        })
        result = parse_language_lesson_response(response)
        assert result["languageNotes"] == "Uses async/await for concurrent operations"
        assert len(result["concepts"]) == 2
        assert result["concepts"][0]["name"] == "async/await"
        assert result["concepts"][0]["explanation"] == "Non-blocking I/O pattern"

    def test_returns_safe_default_on_parse_failure(self) -> None:
        result = parse_language_lesson_response("not valid json")
        assert result["languageNotes"] == ""
        assert result["concepts"] == []

    def test_handles_markdown_wrapped_json(self) -> None:
        response = (
            "```json\n"
            + json.dumps({
                "languageNotes": "Uses decorators",
                "concepts": [{"name": "decorators", "explanation": "Function wrappers"}],
            })
            + "\n```"
        )
        result = parse_language_lesson_response(response)
        assert result["languageNotes"] == "Uses decorators"
        assert result["concepts"][0]["name"] == "decorators"
