"""Search subpackage — fuzzy search and semantic vector search.

Re-exports the main public API from the submodules.
"""

from __future__ import annotations

from understand_anything.search.fuzzy import (
    FuzzyMatch,
    FuzzySearchOptions,
    fuzzy_search,
    fuzzy_search_nodes,
)
from understand_anything.search.semantic import (
    SemanticMatch,
    cosine_similarity,
    search_by_embedding,
)

__all__ = [
    "FuzzyMatch",
    "FuzzySearchOptions",
    "SemanticMatch",
    "cosine_similarity",
    "fuzzy_search",
    "fuzzy_search_nodes",
    "search_by_embedding",
]
