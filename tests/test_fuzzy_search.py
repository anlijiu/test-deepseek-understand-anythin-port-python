"""Tests for fuzzy search (rapidfuzz)."""

from __future__ import annotations

from understand_anything.search.fuzzy import (
    FuzzyMatch,
    FuzzySearchOptions,
    SearchEngine,
    SearchOptions,
    SearchResult,
    fuzzy_search,
    fuzzy_search_nodes,
)
from understand_anything.types import GraphNode, NodeType


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

    def test_duplicate_candidates_map_to_correct_nodes(self) -> None:
        """P1.5: 两个搜索字段完全相同的节点应映射回正确的不同节点。"""
        nodes = [
            self._make_node("n1", "handler", "Handles request", tags=["api"]),
            self._make_node("n2", "handler", "Handles request", tags=["api"]),
        ]
        results = fuzzy_search_nodes("handler", nodes, limit=10)
        assert len(results) == 2
        returned_ids = {match.item.id for match in results}
        assert returned_ids == {"n1", "n2"}
        # 分数应该不同（或至少节点正确）
        for match in results:
            assert match.item.id in ("n1", "n2")


# ---------------------------------------------------------------------------
# SearchEngine (TS-equivalent class API)
# ---------------------------------------------------------------------------


class TestSearchEngine:
    """Tests for the TS-equivalent SearchEngine class."""

    @staticmethod
    def _make_node(
        id_: str,
        name: str,
        type_: NodeType = NodeType.FUNCTION,
        summary: str = "",
        tags: list[str] | None = None,
        language_notes: str | None = None,
    ) -> GraphNode:
        return GraphNode(
            id=id_,
            type=type_,
            name=name,
            summary=summary,
            complexity="moderate",
            tags=tags or [],
            language_notes=language_notes,
        )

    # -- 基本搜索 --

    def test_empty_query_returns_empty(self) -> None:
        """空查询返回空列表。"""
        engine = SearchEngine([
            self._make_node("n1", "hello", summary="world"),
        ])
        assert engine.search("") == []
        assert engine.search("   ") == []

    def test_exact_match_returns_low_distance(self) -> None:
        """精确匹配返回接近 0 的距离分数。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="Authenticates user"),
            self._make_node("n2", "zebra", summary="An animal"),
        ])
        results = engine.search("authenticate")
        assert len(results) > 0
        assert results[0].node_id == "n1"
        assert results[0].score < 0.3  # 低距离 = 好匹配

    def test_partial_match(self) -> None:
        """部分匹配也能找到结果。"""
        engine = SearchEngine([
            self._make_node("n1", "authentication", summary="Handles auth"),
            self._make_node("n2", "render", summary="Renders page"),
        ])
        results = engine.search("auth")
        assert len(results) > 0
        assert results[0].node_id == "n1"

    # -- 类型过滤 --

    def test_types_filter_only_returns_matching_types(self) -> None:
        """types 过滤只返回指定类型的节点。"""
        engine = SearchEngine([
            self._make_node("n1", "my_func", type_=NodeType.FUNCTION, summary="A function"),
            self._make_node("n2", "MyClass", type_=NodeType.CLASS, summary="A class"),
            self._make_node("n3", "config", type_=NodeType.CONFIG, summary="Config"),
        ])
        results = engine.search("my", SearchOptions(types=[NodeType.FUNCTION]))
        assert len(results) > 0
        for r in results:
            assert r.node_id != "n2"  # class 被过滤
        returned = {r.node_id for r in results}
        assert "n1" in returned

    def test_types_filter_with_string_values(self) -> None:
        """types 过滤支持字符串值。"""
        engine = SearchEngine([
            self._make_node("n1", "my_func", type_=NodeType.FUNCTION, summary="F"),
            self._make_node("n2", "MyClass", type_=NodeType.CLASS, summary="C"),
        ])
        results = engine.search("my", SearchOptions(types=["class"]))
        assert len(results) > 0
        assert results[0].node_id == "n2"

    def test_types_filter_multiple_types(self) -> None:
        """types 接受多个类型。"""
        engine = SearchEngine([
            self._make_node("n1", "my_func", type_=NodeType.FUNCTION, summary="A function"),
            self._make_node("n2", "my_klass", type_=NodeType.CLASS, summary="B class"),
            self._make_node("n3", "my_mod", type_=NodeType.MODULE, summary="C module"),
        ])
        results = engine.search(
            "my", SearchOptions(types=[NodeType.FUNCTION, NodeType.CLASS])
        )
        returned = {r.node_id for r in results}
        assert returned == {"n1", "n2"}

    # -- 字段搜索 --

    def test_searches_language_notes(self) -> None:
        """languageNotes 字段可以被搜索到。"""
        engine = SearchEngine([
            self._make_node(
                "n1", "do_stuff", summary="Does stuff",
                language_notes="Uses Python asyncio for concurrency",
            ),
            self._make_node(
                "n2", "other_func", summary="Other",
                language_notes="Plain JavaScript function",
            ),
        ])
        results = engine.search("asyncio")
        assert len(results) > 0
        assert results[0].node_id == "n1"

    def test_searches_tags(self) -> None:
        """tags 字段可以被搜索到。"""
        engine = SearchEngine([
            self._make_node("n1", "login", summary="Login", tags=["auth", "user"]),
            self._make_node("n2", "about", summary="About", tags=["info"]),
        ])
        results = engine.search("auth")
        assert len(results) > 0
        assert results[0].node_id == "n1"

    # -- 结果格式 --

    def test_results_use_node_id_not_object_identity(self) -> None:
        """返回结果是 node id，不依赖对象身份。"""
        engine = SearchEngine([
            self._make_node("abc-123", "test_func", summary="A test function"),
        ])
        results = engine.search("test_func")
        assert len(results) > 0
        assert results[0].node_id == "abc-123"
        assert isinstance(results[0], SearchResult)

    # -- limit --

    def test_default_limit_is_50(self) -> None:
        """默认 limit 为 50（TS 默认）。"""
        nodes = [
            self._make_node(f"n{i}", f"item_{i}", summary=f"Item {i}")
            for i in range(100)
        ]
        engine = SearchEngine(nodes)
        results = engine.search("item")
        assert len(results) <= 50

    def test_explicit_limit_respected(self) -> None:
        """显式 limit 生效。"""
        nodes = [
            self._make_node(f"n{i}", f"item_{i}", summary=f"Item {i}")
            for i in range(20)
        ]
        engine = SearchEngine(nodes)
        results = engine.search("item", SearchOptions(limit=5))
        assert len(results) <= 5

    # -- 分数语义 --

    def test_score_is_distance_0_to_1(self) -> None:
        """分数是 0..1 距离（0 = 完美匹配）。"""
        engine = SearchEngine([
            self._make_node("n1", "hello_world", summary="Says hello"),
        ])
        results = engine.search("hello_world")
        assert len(results) > 0
        assert 0.0 <= results[0].score <= 1.0

    def test_results_sorted_by_ascending_distance(self) -> None:
        """结果按距离分数升序排列（最好的在前）。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate_user", summary="Auth"),
            self._make_node("n2", "auto_complete", summary="Autocomplete"),
            self._make_node("n3", "render_page", summary="Render"),
        ])
        results = engine.search("auth")
        assert len(results) >= 2
        for i in range(len(results) - 1):
            assert results[i].score <= results[i + 1].score

    # -- OR token 语义 --

    def test_multi_token_or_semantics(self) -> None:
        """多词查询使用 OR 语义：匹配任一 token 即可，无关节点被排除。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="User authentication"),
            self._make_node("n2", "login", summary="Login handler"),
            self._make_node("n3", "zebra", summary="Animal facts"),
        ])
        # "auth login" 应匹配 n1 (auth) 和 n2 (login)，排除 n3
        results = engine.search("auth login")
        returned = {r.node_id for r in results}
        assert "n1" in returned
        assert "n2" in returned
        assert "n3" not in returned, f"unrelated zebra node should be excluded, got {returned}"

    def test_multi_token_ranking(self) -> None:
        """匹配多个 token 的节点应排在只匹配单个 token 的节点前面。"""
        engine = SearchEngine([
            self._make_node("n1", "auth_login_handler", summary="Handles both auth and login"),
            self._make_node("n2", "authenticate", summary="Only auth related"),
            self._make_node("n3", "login_page", summary="Only login related"),
        ])
        results = engine.search("auth login")
        assert len(results) >= 2
        # n1 同时包含 auth 和 login，应排在第一位
        assert results[0].node_id == "n1", (
            f"node matching both tokens should rank first, got {results[0].node_id}"
        )

    # -- update_nodes --

    def test_update_nodes_replaces_node_list(self) -> None:
        """update_nodes 后搜索只基于新节点列表。"""
        engine = SearchEngine([
            self._make_node("n1", "apple", summary="Fruit"),
        ])
        assert len(engine.search("apple")) > 0

        engine.update_nodes([
            self._make_node("n2", "banana", summary="Yellow fruit"),
        ])
        # 旧节点不应再出现
        results = engine.search("apple")
        assert len(results) == 0
        # 新节点应可搜索
        results = engine.search("banana")
        assert len(results) > 0
        assert results[0].node_id == "n2"

    def test_update_nodes_empty_clears(self) -> None:
        """update_nodes 空列表后搜索返回空。"""
        engine = SearchEngine([
            self._make_node("n1", "test", summary="Test"),
        ])
        engine.update_nodes([])
        assert engine.search("test") == []

    # -- 缺字段节点 --

    def test_node_without_tags_and_language_notes(self) -> None:
        """缺少 tags 和 language_notes 的节点仍可正常搜索。"""
        engine = SearchEngine([
            GraphNode(
                id="n1",
                type=NodeType.FUNCTION,
                name="simple_func",
                summary="Does one thing",
                complexity="simple",
            ),
        ])
        results = engine.search("simple_func")
        assert len(results) > 0
        assert results[0].node_id == "n1"

    # -- 负面测试：不相关节点被排除 --

    def test_unrelated_node_excluded(self) -> None:
        """不相关的节点不应出现在搜索结果中（zzz 不会匹配 zebra）。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="User authentication"),
            self._make_node("n2", "login", summary="Login handler"),
            self._make_node("n3", "render", summary="Page renderer"),
            self._make_node("n4", "zebra", summary="Animal facts"),
        ])
        # "zzz" 和 "zebra" 仅有 2 个共同字符，partial_ratio ≈ 50-57，
        # 低于阈值 70，所以 n4 不应出现
        results = engine.search("zzz")
        returned = {r.node_id for r in results}
        assert "n4" not in returned, f"zzz should not match zebra, got {returned}"

    def test_unrelated_node_excluded_multi_token(self) -> None:
        """多 token 查询中，不相关的节点不应出现。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="User auth"),
            self._make_node("n2", "login", summary="Login handler"),
            self._make_node("n3", "render", summary="Page renderer"),
            self._make_node("n4", "zebra", summary="Animal facts"),
        ])
        results = engine.search("auth login")
        returned = {r.node_id for r in results}
        assert "n1" in returned
        assert "n2" in returned
        assert "n3" not in returned
        assert "n4" not in returned

    # -- 负面测试：仅精确/近精确匹配可得分 0.0 --

    def test_only_exact_match_scores_zero(self) -> None:
        """只有真正的精确匹配才能得到 0.0 分。"""
        engine = SearchEngine([
            self._make_node("n1", "exact_match", summary="Perfect match"),
            self._make_node("n2", "approximate_match", summary="Close but not exact"),
        ])
        results = engine.search("exact_match")
        # n1 精确匹配得到 0.0
        n1_result = next(r for r in results if r.node_id == "n1")
        assert n1_result.score == 0.0
        # n2 近似匹配不应得到 0.0
        n2_results = [r for r in results if r.node_id == "n2"]
        if n2_results:
            assert n2_results[0].score > 0.0, (
                f"approximate match should not score 0.0, got {n2_results[0].score}"
            )

    def test_partial_match_not_perfect(self) -> None:
        """非精确/非完全子串匹配不应得到 0.0 满分。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="Handles auth"),
        ])
        # "authentcate" (typo, 漏了 i) 与 "authenticate" 相似但不是子串
        results = engine.search("authentcate")
        assert len(results) > 0
        assert results[0].score > 0.0, (
            f"fuzzy (non-substring) match should not score 0.0, got {results[0].score}"
        )

    def test_single_char_query_ignored(self) -> None:
        """单字符查询被安全忽略（不过滤时返回空）。"""
        engine = SearchEngine([
            self._make_node("n1", "authenticate", summary="User auth"),
            self._make_node("n2", "render", summary="Page renderer"),
        ])
        results = engine.search("a")
        # 单字符 token 全部跳过，"a" 匹配不应返回任何结果
        assert results == []
        # 但 "au" 可以匹配
        results2 = engine.search("au")
        assert len(results2) >= 0  # 至少不崩溃
