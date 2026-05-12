"""Analysis modules — graph building, normalisation, and LLM integration.

Layer 4 of the porting plan: graph construction, batch-output normalisation,
and LLM prompt building / response parsing.
"""

from __future__ import annotations

from understand_anything.analysis.graph_builder import (
    KIND_TO_NODE_TYPE,
    GraphBuilder,
)
from understand_anything.analysis.llm_analyzer import (
    LLMFileAnalysis,
    LLMProjectSummary,
    build_file_analysis_prompt,
    build_project_summary_prompt,
    parse_file_analysis_response,
    parse_project_summary_response,
)
from understand_anything.analysis.normalize import (
    DroppedEdge,
    NormalizationStats,
    NormalizeBatchResult,
    normalize_batch_output,
    normalize_complexity,
    normalize_node_id,
)

__all__ = [
    "KIND_TO_NODE_TYPE",
    "DroppedEdge",
    "GraphBuilder",
    "LLMFileAnalysis",
    "LLMProjectSummary",
    "NormalizationStats",
    "NormalizeBatchResult",
    "build_file_analysis_prompt",
    "build_project_summary_prompt",
    "normalize_batch_output",
    "normalize_complexity",
    "normalize_node_id",
    "parse_file_analysis_response",
    "parse_project_summary_response",
]
