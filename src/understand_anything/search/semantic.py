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
from typing import TYPE_CHECKING, Any

import numpy as np

from understand_anything.search.fuzzy import SearchResult
from understand_anything.types import NodeType

if TYPE_CHECKING:
    from understand_anything.types import GraphNode

# Type alias for any numeric vector
Vector = Sequence[float] | np.ndarray


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SemanticMatch:
    """A single semantic-search result."""

    item: Any
    score: float  # cosine similarity 0–1
    index: int = -1  # position in the original candidates list


def _validate_embedding_pair(query_vec: np.ndarray, emb_vec: np.ndarray) -> None:
    """校验 query 和 embedding 向量维度一致。

    Args:
        query_vec: 查询向量（一维）。
        emb_vec: embedding 向量（一维）。

    Raises:
        ValueError: 任一向量非一维，或维度不一致。
    """
    if query_vec.ndim != 1:
        msg = f"query_embedding 必须为一维向量，实际维度为 {query_vec.ndim}"
        raise ValueError(msg)
    if emb_vec.ndim != 1:
        msg = f"embedding 必须为一维向量，实际维度为 {emb_vec.ndim}"
        raise ValueError(msg)
    if query_vec.shape[0] != emb_vec.shape[0]:
        msg = (
            f"query_embedding 维度 ({query_vec.shape[0]}) 与 embedding "
            f"维度 ({emb_vec.shape[0]}) 不一致"
        )
        raise ValueError(msg)


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

    Returns a 1-D array of scores in ``[0, 1]``.
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
        Minimum cosine similarity (0-1) to include a result.
    limit:
        Maximum number of results to return.  ``0`` means unlimited.

    Returns a list of :class:`SemanticMatch` sorted by descending score.
    """
    # 参数校验
    if candidates is not None and len(candidates) != len(embeddings):
        msg = (
            f"candidates 长度 ({len(candidates)}) 与 embeddings 长度 "
            f"({len(embeddings)}) 不一致"
        )
        raise ValueError(msg)

    if not embeddings:
        return []

    query_vec = np.asarray(query_embedding, dtype=np.float64)
    matrix = np.asarray(embeddings, dtype=np.float64)

    # 维度校验
    if query_vec.ndim != 1:
        msg = f"query_embedding 必须为一维向量，实际维度为 {query_vec.ndim}"
        raise ValueError(msg)
    if matrix.ndim != 2:
        msg = f"embeddings 必须为二维矩阵，实际维度为 {matrix.ndim}"
        raise ValueError(msg)
    if matrix.shape[1] != query_vec.shape[0]:
        msg = (
            f"query_embedding 维度 ({query_vec.shape[0]}) 与 embeddings "
            f"行维度 ({matrix.shape[1]}) 不一致"
        )
        raise ValueError(msg)

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


# ---------------------------------------------------------------------------
# SemanticSearchOptions
# ---------------------------------------------------------------------------


@dataclass
class SemanticSearchOptions:
    """:class:`SemanticSearchEngine` 搜索选项。

    Attributes:
        types: 类型过滤 — 仅返回 ``type`` 在此列表中的节点。
            接受 :class:`NodeType` 枚举值或纯字符串。
        limit: 最大返回条数。默认 50。
        threshold: 最小余弦相似度 (0-1)，低于此值的结果被排除。
            默认 0.0（包含所有匹配）。
    """

    types: list[NodeType | str] | None = None
    limit: int = 50
    threshold: float = 0.0


# ---------------------------------------------------------------------------
# SemanticSearchEngine — TS-equivalent class API
# ---------------------------------------------------------------------------


class SemanticSearchEngine:
    """语义向量搜索引擎（对标 TS ``SemanticSearchEngine``）。

    管理 ``node_id → embedding`` 映射，支持对 :class:`GraphNode` 列表
    执行余弦相似度搜索，并提供类型过滤。

    Attributes:
        _nodes: 内部节点列表。
        _embeddings: node_id 到 embedding 向量的映射字典。
    """

    def __init__(
        self,
        nodes: list[GraphNode],
        embeddings: dict[str, list[float]],
    ) -> None:
        """初始化语义搜索引擎。

        Args:
            nodes: 图节点列表。
            embeddings: node_id 到 embedding 向量的映射。
        """
        self._nodes = nodes
        self._embeddings = embeddings

    def has_embeddings(self) -> bool:
        """检查是否有可用的 embedding 数据。

        Returns:
            True 如果至少有一个 embedding。
        """
        return len(self._embeddings) > 0

    def add_embedding(self, node_id: str, embedding: Vector) -> None:
        """添加或覆盖单个节点的 embedding。

        Args:
            node_id: 节点 ID。
            embedding: embedding 向量（float 列表或 numpy 数组）。

        Raises:
            ValueError: embedding 不是一维向量。
        """
        vec_arr = np.asarray(embedding, dtype=np.float64)
        if vec_arr.ndim != 1:
            msg = f"embedding 必须为一维向量，实际维度为 {vec_arr.ndim}"
            raise ValueError(msg)
        self._embeddings[node_id] = list(vec_arr)

    def update_nodes(self, nodes: list[GraphNode]) -> None:
        """替换内部节点列表。

        Args:
            nodes: 新的图节点列表，完全替换旧列表。
        """
        self._nodes = nodes

    def search(
        self,
        query_embedding: Vector,
        options: SemanticSearchOptions | None = None,
    ) -> list[SearchResult]:
        """对当前节点列表执行语义搜索。

        按 node.id 查找 embedding，计算 cosine 相似度，转换为距离分数
        后按升序排列。

        Args:
            query_embedding: 查询向量（float 列表或 numpy 数组）。
            options: 可选搜索参数（类型过滤、条数限制、阈值）。

        Returns:
            按距离分数升序排列的 SearchResult 列表（0 = 最佳匹配）。
        """
        if not self._embeddings or not self._nodes:
            return []

        opts = options or SemanticSearchOptions()

        # 类型过滤集合
        type_filter: set[str] | None = None
        if opts.types:
            type_filter = {
                t.value if isinstance(t, NodeType) else t for t in opts.types
            }

        query_vec = np.asarray(query_embedding, dtype=np.float64)

        results: list[SearchResult] = []
        for node in self._nodes:
            # 类型过滤
            if type_filter is not None and node.type.value not in type_filter:
                continue

            # 按 node.id 查找 embedding
            emb = self._embeddings.get(node.id)
            if emb is None:
                continue

            emb_arr = np.asarray(emb, dtype=np.float64)

            # 维度校验（与 search_by_embedding 共享边界语义）
            _validate_embedding_pair(query_vec, emb_arr)

            # 计算余弦相似度并钳制到 [0, 1]，与 _batch_cosine_similarity
            # 保持一致，确保 distance = 1 - similarity 不越界
            similarity = cosine_similarity(query_vec, emb_arr)
            similarity = max(min(similarity, 1.0), 0.0)

            if similarity < opts.threshold:
                continue

            # 转换为距离分数 (0 = 最佳匹配)
            distance = 1.0 - similarity
            results.append(
                SearchResult(node_id=node.id, score=round(distance, 4))
            )

        # 按距离分数升序（越小越好）
        results.sort(key=lambda r: r.score)

        if opts.limit > 0 and len(results) > opts.limit:
            results = results[: opts.limit]

        return results
