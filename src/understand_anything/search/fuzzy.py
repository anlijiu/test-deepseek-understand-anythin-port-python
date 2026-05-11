"""Fuzzy search powered by rapidfuzz (Python equivalent of fuse.js).

Python port of search.ts.  Uses ``rapidfuzz`` for fast fuzzy matching
instead of fuse.js.  The API is inspired by fuse.js but follows Python
conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from rapidfuzz import fuzz, process

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
        Minimum similarity score (0–100) to include a candidate in results.
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
    key: Optional[str] = None  # which key matched (when searching objects)


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
    options: Optional[FuzzySearchOptions] = None,
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
    processor_func = lambda s: _processor(s, case_sensitive=opts.case_sensitive)

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
    best: dict[int, tuple[Any, float, Optional[str]]] = {}
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
    candidates: list[dict[str, str]] = []
    for node in nodes:
        entry: dict[str, str] = {
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
    # Map back to original GraphNode objects
    for match in matches:
        idx = candidates.index(match.item)  # type: ignore[arg-type]
        match.item = nodes[idx]
    return matches
