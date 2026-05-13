"""Tests for semantic search (cosine similarity)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from understand_anything.search.fuzzy import SearchResult
from understand_anything.search.semantic import (
    SemanticMatch,
    SemanticSearchEngine,
    SemanticSearchOptions,
    cosine_similarity,
    search_by_embedding,
)
from understand_anything.types import GraphNode, NodeType


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-6)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert math.isclose(cosine_similarity(a, b), -1.0, rel_tol=1e-6)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert math.isclose(cosine_similarity(a, b), 0.0, abs_tol=1e-6)

    def test_zero_vector_returns_zero(self) -> None:
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self) -> None:
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_numpy_arrays(self) -> None:
        a = np.array([1.0, 0.0])
        b = np.array([0.5, math.sqrt(3) / 2])
        result = cosine_similarity(a, b)
        assert math.isclose(result, 0.5, rel_tol=1e-6)

    def test_arbitrary_dimension(self) -> None:
        dim = 128
        rng = np.random.default_rng(42)
        v1 = rng.random(dim).tolist()
        v2 = rng.random(dim).tolist()
        score = cosine_similarity(v1, v2)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# search_by_embedding
# ---------------------------------------------------------------------------


class TestSearchByEmbedding:
    @staticmethod
    def _make_embedding(seed: int, dim: int = 64) -> list[float]:
        rng = np.random.default_rng(seed)
        vec = rng.random(dim).astype(np.float64)
        vec /= np.linalg.norm(vec)
        return vec.tolist()

    def test_finds_most_similar(self) -> None:
        embeddings = [
            self._make_embedding(1),  # target
            self._make_embedding(2),
            self._make_embedding(3),
        ]
        query = embeddings[0]  # exact match
        results = search_by_embedding(query, embeddings)
        assert len(results) > 0
        assert results[0].index == 0
        assert math.isclose(results[0].score, 1.0, rel_tol=1e-4)

    def test_threshold_filters(self) -> None:
        embeddings = [self._make_embedding(i) for i in range(10)]
        query = self._make_embedding(0)
        results = search_by_embedding(query, embeddings, threshold=0.99)
        # Only the exact match (if any) should pass
        for r in results:
            assert r.score >= 0.99

    def test_limit_truncates(self) -> None:
        embeddings = [self._make_embedding(i) for i in range(20)]
        query = self._make_embedding(100)  # random, not an exact match for any
        results = search_by_embedding(query, embeddings, threshold=0.0, limit=5)
        assert len(results) <= 5

    def test_returns_original_candidates(self) -> None:
        candidates = ["doc_a", "doc_b", "doc_c"]
        embeddings = [self._make_embedding(i) for i in range(3)]
        results = search_by_embedding(embeddings[1], embeddings, candidates=candidates)
        assert len(results) > 0
        assert results[0].item == "doc_b"

    def test_empty_embeddings(self) -> None:
        assert search_by_embedding([0.5, 0.5], []) == []

    def test_scores_are_descending(self) -> None:
        embeddings = [self._make_embedding(i) for i in range(50)]
        query = self._make_embedding(999)
        results = search_by_embedding(query, embeddings, threshold=0.0)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_zero_embedding_row(self) -> None:
        embeddings = [
            self._make_embedding(1),
            [0.0] * 64,  # zero vector
            self._make_embedding(2),
        ]
        query = self._make_embedding(1)
        results = search_by_embedding(query, embeddings)
        # The zero-vector row should have score 0, or at least not crash
        scores = {r.index: r.score for r in results}
        assert scores.get(1, 0.0) == 0.0 or 1 not in scores

    # -- P1.8 参数校验 --

    def test_candidates_length_mismatch_raises_value_error(self) -> None:
        """candidates 长度与 embeddings 不一致时抛 ValueError。"""
        embeddings = [self._make_embedding(i) for i in range(3)]
        candidates = ["a", "b"]  # 长度 2，embeddings 长度 3
        with pytest.raises(ValueError, match="长度"):
            search_by_embedding(embeddings[0], embeddings, candidates=candidates)

    def test_dimension_mismatch_raises_value_error(self) -> None:
        """query 和 embeddings 维度不一致时抛 ValueError。"""
        embeddings = [self._make_embedding(i, dim=64) for i in range(3)]
        query = [0.5] * 32  # 维度 32，embeddings 维度 64
        with pytest.raises(ValueError, match="维度"):
            search_by_embedding(query, embeddings)

    def test_candidates_length_match_is_ok(self) -> None:
        """candidates 长度与 embeddings 一致时不抛错。"""
        embeddings = [self._make_embedding(i) for i in range(3)]
        candidates = ["a", "b", "c"]
        results = search_by_embedding(embeddings[0], embeddings, candidates=candidates)
        assert len(results) > 0


# ---------------------------------------------------------------------------
# SemanticSearchEngine (TS-equivalent class API)
# ---------------------------------------------------------------------------


class TestSemanticSearchEngine:
    """Tests for the TS-equivalent SemanticSearchEngine class."""

    @staticmethod
    def _make_embedding(seed: int, dim: int = 64) -> list[float]:
        rng = np.random.default_rng(seed)
        vec = rng.random(dim).astype(np.float64)
        vec /= np.linalg.norm(vec)
        return vec.tolist()

    @staticmethod
    def _make_node(
        id_: str,
        name: str,
        type_: NodeType = NodeType.FUNCTION,
        summary: str = "",
    ) -> GraphNode:
        return GraphNode(
            id=id_,
            type=type_,
            name=name,
            summary=summary,
            complexity="moderate",
        )

    # -- has_embeddings --

    def test_has_embeddings_empty(self) -> None:
        """空 embeddings 时 has_embeddings 返回 False。"""
        engine = SemanticSearchEngine(nodes=[], embeddings={})
        assert engine.has_embeddings() is False

    def test_has_embeddings_non_empty(self) -> None:
        """非空 embeddings 时 has_embeddings 返回 True。"""
        engine = SemanticSearchEngine(
            nodes=[], embeddings={"n1": self._make_embedding(1)}
        )
        assert engine.has_embeddings() is True

    # -- add_embedding --

    def test_add_embedding_then_searchable(self) -> None:
        """add_embedding 后节点可被搜索到。"""
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "test_func")],
            embeddings={},
        )
        engine.add_embedding("n1", self._make_embedding(1))
        assert engine.has_embeddings() is True

        query = self._make_embedding(1)  # 与 n1 的 embedding 相同
        results = engine.search(query)
        assert len(results) > 0
        assert results[0].node_id == "n1"
        # 精确匹配：相似度 1.0，距离 0.0
        assert math.isclose(results[0].score, 0.0, abs_tol=1e-4)

    def test_add_embedding_overwrites_existing(self) -> None:
        """对同一 node_id 再次 add_embedding 会覆盖旧值。"""
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "test_func")],
            embeddings={"n1": self._make_embedding(1)},
        )
        # 用不同的 embedding 覆盖
        new_emb = self._make_embedding(999)
        engine.add_embedding("n1", new_emb)
        # 用新的 embedding 查询应得精确匹配
        results = engine.search(new_emb)
        assert results[0].node_id == "n1"
        assert math.isclose(results[0].score, 0.0, abs_tol=1e-4)

    # -- search 基本行为 --

    def test_search_returns_distance_scores_ascending(self) -> None:
        """搜索结果返回距离分数（0 = 最佳匹配），按升序排列。"""
        q_emb = self._make_embedding(1)
        engine = SemanticSearchEngine(
            nodes=[
                self._make_node("n1", "target"),
                self._make_node("n2", "other1"),
                self._make_node("n3", "other2"),
            ],
            embeddings={
                "n1": q_emb,  # 精确匹配
                "n2": self._make_embedding(2),
                "n3": self._make_embedding(3),
            },
        )
        results = engine.search(q_emb)
        assert results[0].node_id == "n1"
        # 分数：0-1 距离，升序
        for i in range(len(results) - 1):
            assert results[i].score <= results[i + 1].score
            assert 0.0 <= results[i].score <= 1.0

    def test_search_skips_nodes_without_embeddings(self) -> None:
        """缺失 embedding 的节点被跳过。"""
        engine = SemanticSearchEngine(
            nodes=[
                self._make_node("n1", "has_emb"),
                self._make_node("n2", "no_emb"),
            ],
            embeddings={"n1": self._make_embedding(1)},
        )
        results = engine.search(self._make_embedding(1))
        returned = {r.node_id for r in results}
        assert "n1" in returned
        assert "n2" not in returned

    def test_search_empty_embeddings_returns_empty(self) -> None:
        """无 embeddings 时搜索返回空列表。"""
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "test")],
            embeddings={},
        )
        assert engine.search(self._make_embedding(1)) == []

    def test_search_empty_nodes_returns_empty(self) -> None:
        """无节点时搜索返回空列表。"""
        engine = SemanticSearchEngine(
            nodes=[],
            embeddings={"n1": self._make_embedding(1)},
        )
        assert engine.search(self._make_embedding(1)) == []

    # -- types 过滤 --

    def test_types_filter_excludes_non_matching(self) -> None:
        """types 过滤排除不匹配的节点类型。"""
        emb = self._make_embedding(1)
        engine = SemanticSearchEngine(
            nodes=[
                self._make_node("n1", "func", type_=NodeType.FUNCTION),
                self._make_node("n2", "klass", type_=NodeType.CLASS),
            ],
            embeddings={"n1": emb, "n2": emb},
        )
        results = engine.search(
            emb, SemanticSearchOptions(types=[NodeType.FUNCTION])
        )
        returned = {r.node_id for r in results}
        assert returned == {"n1"}

    def test_types_filter_with_string_values(self) -> None:
        """types 过滤支持字符串值。"""
        emb = self._make_embedding(1)
        engine = SemanticSearchEngine(
            nodes=[
                self._make_node("n1", "func", type_=NodeType.FUNCTION),
                self._make_node("n2", "klass", type_=NodeType.CLASS),
            ],
            embeddings={"n1": emb, "n2": emb},
        )
        results = engine.search(emb, SemanticSearchOptions(types=["class"]))
        assert len(results) == 1
        assert results[0].node_id == "n2"

    # -- threshold --

    def test_threshold_filters_low_similarity(self) -> None:
        """threshold 过滤低于指定相似度的结果。"""
        q_emb = self._make_embedding(1)
        engine = SemanticSearchEngine(
            nodes=[
                self._make_node("n1", "exact"),
                self._make_node("n2", "similar"),
            ],
            embeddings={
                "n1": q_emb,  # 相似度 1.0
                "n2": self._make_embedding(999),  # 相似度较低
            },
        )
        results = engine.search(q_emb, SemanticSearchOptions(threshold=0.9))
        returned = {r.node_id for r in results}
        assert "n1" in returned
        # n2 相似度低，应被过滤
        assert "n2" not in returned

    # -- limit --

    def test_limit_truncates_results(self) -> None:
        """limit 截断结果。"""
        emb = self._make_embedding(1)
        nodes = [self._make_node(f"n{i}", f"node_{i}") for i in range(10)]
        embeddings = {f"n{i}": self._make_embedding(i + 10) for i in range(10)}
        engine = SemanticSearchEngine(nodes=nodes, embeddings=embeddings)
        results = engine.search(emb, SemanticSearchOptions(limit=3))
        assert len(results) <= 3

    # -- update_nodes --

    def test_update_nodes_replaces_list(self) -> None:
        """update_nodes 后搜索只基于新节点列表。"""
        emb1 = self._make_embedding(1)
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "old_node")],
            embeddings={"n1": emb1},
        )
        assert len(engine.search(emb1)) == 1

        # 替换节点列表 — 旧节点不再存在
        engine.update_nodes([
            self._make_node("n2", "new_node"),
        ])
        # n1 的 embedding 还在，但 n1 不在节点列表中，不应被搜索到
        results = engine.search(emb1)
        assert len(results) == 0

    def test_update_nodes_new_node_with_embedding(self) -> None:
        """update_nodes 后新节点若有 embedding 仍可被搜索。"""
        emb2 = self._make_embedding(2)
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "old")],
            embeddings={"n2": emb2},
        )
        engine.update_nodes([self._make_node("n2", "new")])
        results = engine.search(emb2)
        assert len(results) == 1
        assert results[0].node_id == "n2"

    # -- 负相似度钳制 --

    def test_search_clamps_negative_similarity_to_zero_distance_one(self) -> None:
        """负相似度被钳制为 0，距离 = 1.0，不破坏 [0,1] 距离契约。"""
        node = self._make_node("n1", "f")
        engine = SemanticSearchEngine([node], {"n1": [1.0, 0.0]})
        results = engine.search([-1.0, 0.0])
        assert results == [SearchResult(node_id="n1", score=1.0)]

    # -- 维度校验 --

    def test_search_dimension_mismatch_raises_value_error(self) -> None:
        """query 与 embedding 维度不一致时抛 ValueError，不泄漏 numpy 原始错误。"""
        node = self._make_node("n1", "f")
        engine = SemanticSearchEngine([node], {"n1": [1.0, 0.0]})
        with pytest.raises(ValueError, match="维度"):
            engine.search([1.0, 0.0, 0.0])

    def test_add_embedding_non_1d_raises_value_error(self) -> None:
        """add_embedding 传入多维数组时抛 ValueError。"""
        engine = SemanticSearchEngine(
            nodes=[self._make_node("n1", "f")],
            embeddings={},
        )
        with pytest.raises(ValueError, match="一维"):
            engine.add_embedding("n1", [[1.0, 0.0], [0.0, 1.0]])
