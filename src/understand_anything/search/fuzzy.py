"""Fuzzy search powered by rapidfuzz (Python equivalent of fuse.js).

Python port of search.ts.  Uses ``rapidfuzz`` for fast fuzzy matching
instead of fuse.js.  The API is inspired by fuse.js but follows Python
conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from rapidfuzz import fuzz

from understand_anything.types import NodeType

if TYPE_CHECKING:
    from understand_anything.types import GraphNode

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FuzzySearchOptions:
    """Options controlling fuzzy search behaviour.

    Attributes
    ----------
    threshold:
        Minimum similarity score (0-100) to include a candidate in results.
        Default 60 (roughly equivalent to Fuse.js 0.6 threshold).
    limit:
        Maximum number of results to return.  ``0`` means unlimited.
    case_sensitive:
        Whether to consider case when matching.  Default ``False``.
    keys:
        Object keys to search within each candidate.  If empty, candidates
        are matched as plain strings.
    weights:
        Per-key weight multipliers.  Keys not listed default to 1.0.
    """

    threshold: float = 60.0
    limit: int = 20
    case_sensitive: bool = False
    keys: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class FuzzyMatch:
    """A single fuzzy-match result."""

    item: Any
    score: float  # 0–100
    key: str | None = None  # which key matched (when searching objects)


@dataclass
class SearchOptions:
    """:class:`SearchEngine` 搜索选项（对标 TS SearchOptions）。

    Attributes:
        types: 类型过滤 — 仅返回 ``type`` 在此列表中的节点。
            接受 :class:`NodeType` 枚举值或纯字符串。
        limit: 最大返回条数。默认 50（TS 默认值）。
    """

    types: list[NodeType | str] | None = None
    limit: int = 50


@dataclass
class SearchResult:
    """:class:`SearchEngine` 单条搜索结果（对标 TS SearchResult）。

    Attributes:
        node_id: 匹配到的 :class:`GraphNode` 的 ``id``。
        score: 距离分数，范围 ``[0, 1]``，``0`` 表示完美匹配，
            ``1`` 表示最差匹配（兼容 TS fuse.js 距离语义）。
    """

    node_id: str
    score: float  # 0..1 distance


# ---------------------------------------------------------------------------
# Core search
# ---------------------------------------------------------------------------


def _extract_candidates(
    candidates: list[Any], keys: list[str]
) -> dict[int, dict[str, str]]:
    """Build a lookup table: candidate_index → {key: value_string}.

    Only entries where *value_string* is non-empty are kept.
    """
    lookup: dict[int, dict[str, str]] = {}
    for i, candidate in enumerate(candidates):
        entry: dict[str, str] = {}
        for key in keys:
            val = candidate.get(key) if isinstance(candidate, dict) else getattr(candidate, key, None)
            if val is not None and str(val).strip():
                entry[key] = str(val)
        if entry:
            lookup[i] = entry
    return lookup


def _processor(s: str, *, case_sensitive: bool) -> str:
    """Normalise a string for comparison."""
    return s if case_sensitive else s.lower()


def fuzzy_search(
    query: str,
    candidates: list[Any],
    options: FuzzySearchOptions | None = None,
) -> list[FuzzyMatch]:
    """Search *candidates* for *query* using fuzzy string matching.

    Parameters
    ----------
    query:
        The search string.
    candidates:
        A list of strings, dicts, or objects.  When dicts/objects are
        provided you must also set ``keys`` in *options*.
    options:
        Search parameters (threshold, limit, keys, etc.).

    Returns a list of :class:`FuzzyMatch` sorted by descending score.
    """
    opts = options or FuzzySearchOptions()

    def processor_func(s: str) -> str:
        return _processor(s, case_sensitive=opts.case_sensitive)

    # String-only path — simplest and fastest
    if not opts.keys:
        processed_query = processor_func(query)
        results: list[FuzzyMatch] = []
        for candidate in candidates:
            if isinstance(candidate, str):
                score = fuzz.token_sort_ratio(
                    processed_query, processor_func(candidate)
                )
                if score >= opts.threshold:
                    results.append(FuzzyMatch(item=candidate, score=score))
        results.sort(key=lambda m: m.score, reverse=True)
        if opts.limit > 0:
            results = results[: opts.limit]
        return results

    # Object path — extract candidate strings per key
    lookup = _extract_candidates(candidates, opts.keys)
    processed_query = processor_func(query)

    # Collect all (candidate_index, key, value_str, score)
    scored: list[tuple[int, str, str, float]] = []
    for idx, key_values in lookup.items():
        for key, value_str in key_values.items():
            weight = opts.weights.get(key, 1.0)
            score = fuzz.token_sort_ratio(
                processed_query, processor_func(value_str)
            )
            if score >= opts.threshold:
                scored.append((idx, key, value_str, score * weight))

    # Keep best score per candidate
    best: dict[int, tuple[Any, float, str | None]] = {}
    for idx, key, _value_str, weighted_score in scored:
        if idx not in best or weighted_score > best[idx][1]:
            best[idx] = (candidates[idx], weighted_score, key)

    matches = [
        FuzzyMatch(item=item, score=round(score, 1), key=key)
        for item, score, key in best.values()
    ]
    matches.sort(key=lambda m: m.score, reverse=True)

    if opts.limit > 0:
        matches = matches[: opts.limit]
    return matches


# ---------------------------------------------------------------------------
# Graph-node-specific convenience
# ---------------------------------------------------------------------------


def fuzzy_search_nodes(
    query: str,
    nodes: list[GraphNode],
    *,
    threshold: float = 60.0,
    limit: int = 20,
    case_sensitive: bool = False,
    search_tags: bool = True,
) -> list[FuzzyMatch]:
    """Fuzzy search across a list of :class:`GraphNode` objects.

    Searches the ``name``, ``summary``, and (optionally) ``tags`` fields.
    """
    keys = ["name", "summary"]
    weights: dict[str, float] = {"name": 2.0, "summary": 0.8}
    if search_tags:
        keys.append("tags")
        weights["tags"] = 2.5

    # tags is a list — flatten to a searchable string per node
    # _node_idx tracks original index to avoid candidates.index() bug
    # when two nodes have identical search fields.
    candidates: list[dict[str, str]] = []
    for i, node in enumerate(nodes):
        entry: dict[str, str] = {
            "_node_idx": str(i),
            "name": node.name,
            "summary": node.summary,
        }
        if search_tags and node.tags:
            entry["tags"] = " ".join(node.tags)
        candidates.append(entry)

    options = FuzzySearchOptions(
        threshold=threshold,
        limit=limit,
        case_sensitive=case_sensitive,
        keys=keys,
        weights=weights,
    )

    matches = fuzzy_search(query, candidates, options)
    # Map back to original GraphNode objects using tracked index
    for match in matches:
        idx = int(match.item["_node_idx"])
        match.item = nodes[idx]
    return matches


# ---------------------------------------------------------------------------
# SearchEngine — TS-equivalent class API
# ---------------------------------------------------------------------------


class SearchEngine:
    """图节点模糊搜索引擎（对标 TS ``SearchEngine``）。

    提供类型过滤、多词查询的 OR token 语义，以及兼容 fuse.js 的距离分数。

    Attributes:
        _nodes: 内部节点列表，用于搜索。
    """

    # Field weights for scoring (higher = more important)
    _FIELD_WEIGHTS: ClassVar[dict[str, float]] = {
        "name": 2.0,
        "tags": 2.5,
        "summary": 0.8,
        "language_notes": 1.0,
    }

    def __init__(self, nodes: list[GraphNode]) -> None:
        """初始化搜索引擎。

        Args:
            nodes: 要搜索的图节点列表。
        """
        self._nodes = nodes

    def update_nodes(self, nodes: list[GraphNode]) -> None:
        """替换内部节点列表。

        Args:
            nodes: 新的图节点列表，完全替换旧列表。
        """
        self._nodes = nodes

    def search(
        self, query: str, options: SearchOptions | None = None
    ) -> list[SearchResult]:
        """对当前节点列表执行模糊搜索。

        支持 OR token 语义：多词查询会按空白字符拆分为独立 token，
        每个 token 独立匹配，最终取跨所有 token 和字段的最佳分数。

        Args:
            query: 搜索查询字符串。空白查询返回空列表。
            options: 可选搜索参数（类型过滤、条数限制）。

        Returns:
            按距离分数升序排列的 SearchResult 列表（0 = 最佳匹配）。
        """
        if not query.strip():
            return []

        opts = options or SearchOptions()

        # 类型过滤集合
        type_filter: set[str] | None = None
        if opts.types:
            type_filter = {t.value if isinstance(t, NodeType) else t for t in opts.types}

        # 按空白拆分 token（OR 语义）
        tokens = query.strip().split()

        results: list[SearchResult] = []

        for node in self._nodes:
            # 类型过滤
            if type_filter is not None and node.type.value not in type_filter:
                continue

            # 构建 node 的搜索字段
            fields: dict[str, str] = {
                "name": node.name,
                "summary": node.summary,
            }
            if node.tags:
                fields["tags"] = " ".join(node.tags)
            if node.language_notes:
                fields["language_notes"] = node.language_notes

            # OR 语义：每个 token 独立匹配。
            # 最终分数为所有 token 最佳距离的均值，使匹配更多 token 的节点排名更靠前。
            per_token_best: list[float] = []
            for token in tokens:
                # 单字符 token 过于模糊，跳过
                if len(token) < 2:
                    continue
                token_lower = token.lower()
                best_for_token = 1.0  # 默认：未匹配（最远距离）
                for field_key, field_value in fields.items():
                    raw = fuzz.partial_ratio(token_lower, field_value.lower())
                    # 最低 70 分阈值，等价于 fuzzy_search 默认 60 + 余量
                    if raw < 70:
                        continue
                    weight = self._FIELD_WEIGHTS.get(field_key, 1.0)
                    # 先转为距离 (0..1)，再除以权重：高权重 → 低距离 → 排名更靠前
                    # 权重不能把弱匹配变成完美匹配
                    raw_distance = 1.0 - (raw / 100.0)
                    weighted_distance = raw_distance / weight
                    if weighted_distance < best_for_token:
                        best_for_token = weighted_distance
                per_token_best.append(best_for_token)

            # OR 语义：至少一个 token 匹配则入选
            if per_token_best and min(per_token_best) < 1.0:
                final_distance = sum(per_token_best) / len(per_token_best)
                results.append(
                    SearchResult(
                        node_id=node.id,
                        score=round(final_distance, 4),
                    )
                )

        # 按距离分数升序（越小越好）
        results.sort(key=lambda r: r.score)

        if opts.limit > 0 and len(results) > opts.limit:
            results = results[: opts.limit]

        return results
