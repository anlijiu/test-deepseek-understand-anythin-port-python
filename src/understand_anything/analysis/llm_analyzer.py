"""LLM analyzer — prompt builders and response parsers for AI-assisted analysis.

Python port of the TypeScript ``llm-analyzer.ts``.  Provides functions to:

1. Generate prompts for file-level and project-level LLM analysis.
2. Parse and validate LLM JSON responses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ===========================================================================
# Data structures
# ===========================================================================


@dataclass
class LLMFileAnalysis:
    """Parsed result of a file-level LLM analysis."""

    file_summary: str
    tags: list[str] = field(default_factory=list)
    complexity: str = "moderate"  # "simple" | "moderate" | "complex"
    function_summaries: dict[str, str] = field(default_factory=dict)
    class_summaries: dict[str, str] = field(default_factory=dict)
    language_notes: str | None = None


@dataclass
class LLMProjectSummary:
    """Parsed result of a project-level LLM analysis."""

    description: str
    frameworks: list[str] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)


# ===========================================================================
# Validation constants
# ===========================================================================

_VALID_COMPLEXITIES: set[str] = {"simple", "moderate", "complex"}


# ===========================================================================
# Prompt builders
# ===========================================================================


def build_file_analysis_prompt(
    file_path: str,
    content: str,
    project_context: str,
) -> str:
    """Generate an LLM prompt for analyzing a single source file.

    Args:
        file_path: Path to the file being analyzed.
        content: Full source text of the file.
        project_context: Brief description of the project for context.

    Returns:
        A prompt string ready to send to an LLM.
    """
    return (
        f"You are a code analysis assistant. Analyze the following source"
        f" file and return a JSON object.\n\n"
        f"Project context: {project_context}\n\n"
        f"File: {file_path}\n\n"
        f"```\n{content}\n```\n\n"
        f"Return a JSON object with the following fields:\n"
        f'- "fileSummary": A concise summary of what this file does'
        f" (1-2 sentences).\n"
        f'- "tags": An array of relevant tags'
        f' (e.g., ["utility", "async", "api"]).\n'
        f'- "complexity": One of "simple", "moderate", or "complex".\n'
        f'- "functionSummaries": An object mapping function names to'
        f" 1-sentence summaries.\n"
        f'- "classSummaries": An object mapping class names to'
        f" 1-sentence summaries.\n"
        f'- "languageNotes": Optional notes about language-specific'
        f" patterns or idioms used.\n\n"
        f"Respond ONLY with the JSON object, no additional text."
    )


def build_project_summary_prompt(
    file_list: list[str],
    sample_files: list[dict[str, str]],
) -> str:
    """Generate an LLM prompt for creating a project-level summary.

    Args:
        file_list: List of file paths in the project.
        sample_files: List of dicts with ``"path"`` and ``"content"`` keys
            for a subset of files to include as samples.

    Returns:
        A prompt string ready to send to an LLM.
    """
    file_list_str = "\n".join(f"  - {f}" for f in file_list)

    samples_str = ""
    if sample_files:
        samples_str = "\n\nSample files:\n"
        for sample in sample_files:
            samples_str += (
                f"\n--- {sample['path']} ---\n"
                f"```\n{sample['content']}\n```\n"
            )

    return (
        f"You are a code analysis assistant. Analyze the following project"
        f" structure and return a JSON object describing the project.\n\n"
        f"File list:\n{file_list_str}{samples_str}\n"
        f"Return a JSON object with the following fields:\n"
        f'- "description": A concise description of what this project'
        f" does (2-3 sentences).\n"
        f'- "frameworks": An array of frameworks and major libraries'
        f' detected (e.g., ["React", "Express", "Vitest"]).\n'
        f'- "layers": An array of logical layers, each with:\n'
        f'  - "name": The layer name (e.g., "API", "Data", "UI").\n'
        f'  - "description": What this layer is responsible for.\n'
        f'  - "filePatterns": Glob patterns or path prefixes that'
        f" belong to this layer.\n\n"
        f"Respond ONLY with the JSON object, no additional text."
    )


# ===========================================================================
# JSON extraction
# ===========================================================================


def _extract_json(response: str) -> str:
    """Extract a JSON block from an LLM response.

    Handles markdown code fences (with or without ``json`` tag) and
    bare JSON objects.

    Args:
        response: Raw LLM response text.

    Returns:
        The extracted JSON string, trimmed.
    """
    # Try to extract from markdown code fences
    fence_match = re.search(
        r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", response
    )
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find a raw JSON object
    object_match = re.search(r"\{[\s\S]*\}", response)
    if object_match:
        return object_match.group(0).strip()

    return response.strip()


# ===========================================================================
# Response parsers
# ===========================================================================


def parse_file_analysis_response(response: str) -> LLMFileAnalysis | None:
    """Parse an LLM response into an :class:`LLMFileAnalysis`.

    Args:
        response: Raw LLM response text.

    Returns:
        An ``LLMFileAnalysis`` on success, or ``None`` if parsing fails.
    """
    try:
        json_str = _extract_json(response)
        parsed: dict[str, Any] = json.loads(json_str)

        # Validate and normalize complexity
        complexity: str = "moderate"
        raw_complexity = parsed.get("complexity")
        if isinstance(raw_complexity, str) and raw_complexity in _VALID_COMPLEXITIES:
            complexity = raw_complexity

        return LLMFileAnalysis(
            file_summary=(
                parsed["fileSummary"]
                if isinstance(parsed.get("fileSummary"), str)
                else ""
            ),
            tags=(
                [
                    t
                    for t in parsed.get("tags", [])
                    if isinstance(t, str)
                ]
                if isinstance(parsed.get("tags"), list)
                else []
            ),
            complexity=complexity,
            function_summaries=(
                parsed["functionSummaries"]
                if isinstance(parsed.get("functionSummaries"), dict)
                else {}
            ),
            class_summaries=(
                parsed["classSummaries"]
                if isinstance(parsed.get("classSummaries"), dict)
                else {}
            ),
            language_notes=(
                parsed["languageNotes"]
                if isinstance(parsed.get("languageNotes"), str)
                else None
            ),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def parse_project_summary_response(
    response: str,
) -> LLMProjectSummary | None:
    """Parse an LLM response into an :class:`LLMProjectSummary`.

    Args:
        response: Raw LLM response text.

    Returns:
        An ``LLMProjectSummary`` on success, or ``None`` if parsing fails.
    """
    try:
        json_str = _extract_json(response)
        parsed: dict[str, Any] = json.loads(json_str)

        raw_layers = parsed.get("layers")
        layers: list[dict[str, Any]] = (
            [
                {
                    "name": layer["name"],
                    "description": (
                        layer["description"]
                        if isinstance(layer.get("description"), str)
                        else ""
                    ),
                    "filePatterns": (
                        [
                            p
                            for p in layer.get("filePatterns", [])
                            if isinstance(p, str)
                        ]
                        if isinstance(layer.get("filePatterns"), list)
                        else []
                    ),
                }
                for layer in raw_layers
                if isinstance(layer, dict) and isinstance(layer.get("name"), str)
            ]
            if isinstance(raw_layers, list)
            else []
        )

        return LLMProjectSummary(
            description=(
                parsed["description"]
                if isinstance(parsed.get("description"), str)
                else ""
            ),
            frameworks=(
                [
                    f
                    for f in parsed.get("frameworks", [])
                    if isinstance(f, str)
                ]
                if isinstance(parsed.get("frameworks"), list)
                else []
            ),
            layers=layers,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
