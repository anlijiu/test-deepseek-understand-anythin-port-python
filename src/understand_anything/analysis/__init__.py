"""Analysis modules — graph building, normalisation, LLM integration, and
advanced analysis.

Layers 4-5 of the porting plan: graph construction, batch-output normalisation,
LLM prompt building / response parsing, layer detection, tour generation,
language lessons, file fingerprinting, staleness checks, and change
classification.
"""

from __future__ import annotations

from understand_anything.analysis.change_classifier import (
    UpdateDecision,
    classify_update,
)
from understand_anything.analysis.fingerprint import (
    ChangeAnalysis,
    FileChangeResult,
    FileFingerprint,
    FingerprintStore,
    compare_fingerprints,
    content_hash,
    extract_file_fingerprint,
)
from understand_anything.analysis.graph_builder import (
    KIND_TO_NODE_TYPE,
    GraphBuilder,
)
from understand_anything.analysis.language_lesson import (
    build_language_lesson_prompt,
    detect_language_concepts,
    get_language_display_name,
    parse_language_lesson_response,
)
from understand_anything.analysis.layer_detector import (
    apply_llm_layers,
    build_layer_detection_prompt,
    detect_layers,
    parse_layer_detection_response,
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
from understand_anything.analysis.staleness import (
    get_changed_files,
    is_stale,
    merge_graph_update,
)
from understand_anything.analysis.tour_generator import (
    build_tour_generation_prompt,
    generate_heuristic_tour,
    parse_tour_generation_response,
)

__all__ = [
    "KIND_TO_NODE_TYPE",
    # fingerprint
    "ChangeAnalysis",
    # normalize
    "DroppedEdge",
    "FileChangeResult",
    "FileFingerprint",
    "FingerprintStore",
    # graph_builder
    "GraphBuilder",
    # llm_analyzer
    "LLMFileAnalysis",
    "LLMProjectSummary",
    "NormalizationStats",
    "NormalizeBatchResult",
    # change_classifier
    "UpdateDecision",
    # layer_detector
    "apply_llm_layers",
    "build_file_analysis_prompt",
    # language_lesson
    "build_language_lesson_prompt",
    "build_layer_detection_prompt",
    "build_project_summary_prompt",
    # tour_generator
    "build_tour_generation_prompt",
    "classify_update",
    "compare_fingerprints",
    "content_hash",
    "detect_language_concepts",
    "detect_layers",
    "extract_file_fingerprint",
    "generate_heuristic_tour",
    # staleness
    "get_changed_files",
    "get_language_display_name",
    "is_stale",
    "merge_graph_update",
    "normalize_batch_output",
    "normalize_complexity",
    "normalize_node_id",
    "parse_file_analysis_response",
    "parse_language_lesson_response",
    "parse_layer_detection_response",
    "parse_project_summary_response",
    "parse_tour_generation_response",
]
