"""Tests for semantic search (cosine similarity)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from understand_anything.search.semantic import (
    SemanticMatch,
    cosine_similarity,
    search_by_embedding,
)


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
