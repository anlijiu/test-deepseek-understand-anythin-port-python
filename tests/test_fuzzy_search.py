"""Tests for fuzzy search (rapidfuzz)."""

from __future__ import annotations

from understand_anything.search.fuzzy import (
    FuzzyMatch,
    FuzzySearchOptions,
    fuzzy_search,
    fuzzy_search_nodes,
)
from understand_anything.types import GraphNode


# ---------------------------------------------------------------------------
# String search
# ---------------------------------------------------------------------------


class TestFuzzySearchStrings:
    def test_exact_match(self) -> None:
        results = fuzzy_search("hello", ["hello", "world", "help"])
        assert len(results) > 0
        assert results[0].item == "hello"
        assert results[0].score >= 90

    def test_partial_match(self) -> None:
        results = fuzzy_search("helo", ["hello", "world", "help"])
        assert len(results) > 0
        # "hello" should be the best match
        assert results[0].item == "hello"

    def test_threshold_filters_low_scores(self) -> None:
        results = fuzzy_search(
            "xyz",
            ["hello", "world", "completely", "different", "words"],
            FuzzySearchOptions(threshold=80),
        )
        assert len(results) == 0

    def test_limit_truncates(self) -> None:
        candidates = ["apple", "app", "application", "apply", "apricot"]
        results = fuzzy_search("app", candidates, FuzzySearchOptions(limit=3))
        assert len(results) <= 3

    def test_case_insensitive_by_default(self) -> None:
        results = fuzzy_search("HELLO", ["Hello", "world"])
        assert len(results) > 0
        assert results[0].item == "Hello"

    def test_case_sensitive_option(self) -> None:
        results = fuzzy_search(
            "HELLO",
            ["Hello", "HELLO", "hello"],
            FuzzySearchOptions(case_sensitive=True, threshold=50),
        )
        assert len(results) > 0
        assert results[0].item == "HELLO"


# ---------------------------------------------------------------------------
# Dict / object search
# ---------------------------------------------------------------------------


class TestFuzzySearchObjects:
    def test_searches_specific_keys(self) -> None:
        candidates = [
            {"name": "main.py", "path": "src/main.py"},
            {"name": "utils.py", "path": "src/utils.py"},
            {"name": "README.md", "path": "README.md"},
        ]
        results = fuzzy_search(
            "main",
            candidates,
            FuzzySearchOptions(keys=["name"], threshold=60),
        )
        assert len(results) > 0
        assert results[0].item["name"] == "main.py"
        assert results[0].key == "name"

    def test_respects_key_weights(self) -> None:
        candidates = [
            {"title": "hello", "body": "some irrelevant long text about other things"},
            {"title": "other topic", "body": "hello world hello again"},
        ]
        results = fuzzy_search(
            "hello",
            candidates,
            FuzzySearchOptions(
                keys=["title", "body"],
                weights={"title": 10.0, "body": 1.0},
                threshold=50,
            ),
        )
        assert results[0].item["title"] == "hello"

    def test_skips_empty_values(self) -> None:
        candidates = [
            {"name": "", "desc": "hello world"},
            {"name": "world", "desc": ""},
        ]
        results = fuzzy_search(
            "hello",
            candidates,
            FuzzySearchOptions(keys=["name", "desc"], threshold=60),
        )
        # Should match the first candidate via "desc"
        assert len(results) > 0


# ---------------------------------------------------------------------------
# GraphNode-specific search
# ---------------------------------------------------------------------------


class TestFuzzySearchNodes:
    @staticmethod
    def _make_node(id_: str, name: str, summary: str, tags: list[str] | None = None) -> GraphNode:
        return GraphNode(
            id=id_,
            type="function",
            name=name,
            summary=summary,
            complexity="moderate",
            tags=tags or [],
        )

    def test_searches_nodes(self) -> None:
        nodes = [
            self._make_node("n1", "authenticate", "Authenticates a user"),
            self._make_node("n2", "authorize", "Checks user permissions"),
            self._make_node("n3", "render_page", "Renders HTML template"),
        ]
        results = fuzzy_search_nodes("auth", nodes)
        assert len(results) > 0
        assert results[0].item.name in ("authenticate", "authorize")

    def test_searches_tags(self) -> None:
        nodes = [
            self._make_node("n1", "login", "Login page", tags=["auth", "user"]),
            self._make_node("n2", "about", "About page", tags=["info"]),
        ]
        results = fuzzy_search_nodes("auth", nodes, search_tags=True)
        assert len(results) > 0
        assert results[0].item.name == "login"

    def test_can_disable_tag_search(self) -> None:
        nodes = [
            self._make_node("n1", "login", "Login page", tags=["auth"]),
        ]
        results = fuzzy_search_nodes("auth", nodes, search_tags=False)
        # "auth" won't match "login" name/summary well
        assert len(results) == 0 or results[0].score < 50

    def test_threshold_respected(self) -> None:
        nodes = [
            self._make_node("n1", "apple", "A fruit"),
            self._make_node("n2", "zebra", "An animal"),
        ]
        results = fuzzy_search_nodes("apple", nodes, threshold=90)
        assert len(results) > 0
        assert results[0].item.name == "apple"

    def test_limit_truncates_node_results(self) -> None:
        nodes = [
            self._make_node(f"n{i}", f"user_{i}", f"User function {i}")
            for i in range(10)
        ]
        results = fuzzy_search_nodes("user", nodes, limit=5)
        assert len(results) <= 5
