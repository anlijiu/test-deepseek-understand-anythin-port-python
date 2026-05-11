"""Semantic (vector) search with cosine similarity.

Python port of embedding-search.ts.  Uses ``numpy`` for vectorised cosine
similarity computation.  This module is intentionally lightweight — it
does NOT depend on any embedding provider.  Embeddings are generated
externally (e.g. via sentence-transformers, OpenAI, or Ollama) and passed
in as plain ``list[float]`` / numpy arrays.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Union

import numpy as np

# Type alias for any numeric vector
Vector = Union[Sequence[float], np.ndarray]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SemanticMatch:
    """A single semantic-search result."""

    item: Any
    score: float  # cosine similarity 0–1
    index: int = -1  # position in the original candidates list


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Compute cosine similarity between two vectors.

    Returns a value in ``[0, 1]``.  Zero vectors produce ``0.0``.
    """
    a_arr = np.asarray(a, dtype=np.float64)
    b_arr = np.asarray(b, dtype=np.float64)

    a_norm = np.linalg.norm(a_arr)
    b_norm = np.linalg.norm(b_arr)

    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0

    return float(np.dot(a_arr, b_arr) / (a_norm * b_norm))


def _batch_cosine_similarity(
    query_vec: np.ndarray, matrix: np.ndarray
) -> np.ndarray:
    """Compute cosine similarity between a query vector and every row in *matrix*.

    Returns a 1‑D array of scores in ``[0, 1]``.
    """
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0.0:
        return np.zeros(matrix.shape[0], dtype=np.float64)

    row_norms = np.linalg.norm(matrix, axis=1)
    # Avoid division by zero for zero rows
    safe_norms = np.where(row_norms == 0.0, 1.0, row_norms)
    dots = np.dot(matrix, query_vec)
    scores = dots / (safe_norms * q_norm)
    # Zero rows get score 0
    scores[row_norms == 0.0] = 0.0
    return np.clip(scores, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_by_embedding(
    query_embedding: Vector,
    embeddings: list[Vector],
    candidates: list[Any] | None = None,
    *,
    threshold: float = 0.5,
    limit: int = 20,
) -> list[SemanticMatch]:
    """Find the *candidates* most similar to *query_embedding*.

    Parameters
    ----------
    query_embedding:
        The query vector (list of floats or numpy array).
    embeddings:
        Embedding vectors for each candidate.  Must have the same length as
        *candidates* (when provided).
    candidates:
        Original items corresponding to *embeddings*.  If ``None``, the
        indices are used as the items.
    threshold:
        Minimum cosine similarity (0–1) to include a result.
    limit:
        Maximum number of results to return.  ``0`` means unlimited.

    Returns a list of :class:`SemanticMatch` sorted by descending score.
    """
    if not embeddings:
        return []

    matrix = np.asarray(embeddings, dtype=np.float64)
    query_vec = np.asarray(query_embedding, dtype=np.float64)

    scores = _batch_cosine_similarity(query_vec, matrix)

    # Collect matches above threshold
    results: list[SemanticMatch] = []
    for i, score in enumerate(scores):
        if score >= threshold:
            item = candidates[i] if candidates else i
            results.append(SemanticMatch(item=item, score=round(float(score), 4), index=i))

    results.sort(key=lambda m: m.score, reverse=True)

    if limit > 0:
        results = results[:limit]
    return results
