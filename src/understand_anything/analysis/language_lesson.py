"""Concept detection + lesson prompt builders for language-specific education.

Python port of the TypeScript ``language-lesson.ts``. Detects language
concepts (async/await, dependency injection, etc.) from node metadata and
builds LLM prompts for generating language-specific educational lessons.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from understand_anything.types import GraphEdge

from understand_anything.types import GraphNode  # noqa: TC001

# ===========================================================================
# Concept pattern definitions
# ===========================================================================

# Base concept patterns that apply across all languages.
# These are merged with language-specific concepts when available.
_BASE_CONCEPT_PATTERNS: dict[str, list[str]] = {
    "async/await": ["async", "await", "promise", "asynchronous"],
    "middleware pattern": ["middleware", "interceptor", "pipe"],
    "generics": ["generic", "type parameter", "template"],
    "decorators": ["decorator", "@", "annotation"],
    "dependency injection": ["inject", "provider", "container", "di"],
    "observer pattern": [
        "subscribe", "publish", "event", "observable", "listener",
    ],
    "singleton": ["singleton", "instance", "shared client"],
    "type guards": [
        "type guard", "is", "narrowing", "discriminated union",
    ],
    "higher-order functions": [
        "callback", "factory", "higher-order", "closure",
    ],
    "error handling": [
        "try/catch", "error boundary", "exception", "Result type",
    ],
    "streams": [
        "stream", "pipe", "transform", "readable", "writable",
    ],
    "concurrency": [
        "goroutine", "channel", "thread", "worker", "mutex",
    ],
}


def _build_concept_patterns(
    lang_config: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Merge base concept patterns with language-specific concepts if provided."""
    patterns = dict(_BASE_CONCEPT_PATTERNS)

    if lang_config:
        concepts = lang_config.get("concepts")
        if isinstance(concepts, list):
            for concept in concepts:
                if isinstance(concept, str) and concept not in patterns:
                    patterns[concept] = [concept.lower()]

    return patterns


# ===========================================================================
# Concept detection
# ===========================================================================


def detect_language_concepts(
    node: GraphNode,
    language: str,
    lang_config: dict[str, Any] | None = None,
) -> list[str]:
    """Detect language concepts present in a graph node.

    Checks the node's tags, summary, and language_notes against known
    concept keyword patterns.
    """
    text = " ".join(
        [
            *node.tags,
            node.summary.lower(),
            (node.language_notes or "").lower(),
        ]
    )

    patterns = _build_concept_patterns(lang_config)
    detected: list[str] = []

    for concept, keywords in patterns.items():
        if any(
            keyword.lower() in text.lower() for keyword in keywords
        ):
            detected.append(concept)

    return detected


# ===========================================================================
# Language display name
# ===========================================================================


def get_language_display_name(
    language: str,
    lang_config: dict[str, Any] | None = None,
) -> str:
    """Get the display name for a language.

    Uses ``displayName`` from the config if provided, otherwise capitalises.
    """
    if lang_config and isinstance(lang_config.get("displayName"), str):
        return str(lang_config["displayName"])
    return language.capitalize()


# ===========================================================================
# LLM prompt building
# ===========================================================================


def build_language_lesson_prompt(
    node: GraphNode,
    edges: list[GraphEdge],
    language: str,
    lang_config: dict[str, Any] | None = None,
) -> str:
    """Build a prompt that asks an LLM for a language-specific lesson.

    Args:
        node: The graph node to explain.
        edges: Edges connected to this node.
        language: The programming language.
        lang_config: Optional language configuration dict.
    """
    capitalized = get_language_display_name(language, lang_config)
    concepts = detect_language_concepts(node, language, lang_config)

    # Build relationship descriptions
    relationship_lines: list[str] = []
    for edge in edges:
        arrow = "->" if edge.direction == "forward" else "<-"
        other = edge.target if edge.source == node.id else edge.source
        relationship_lines.append(f"  {arrow} {edge.type.value} {other}")
    relationships = "\n".join(relationship_lines)

    if concepts:
        concept_section = (
            "\nDetected concepts to explain:\n"
            + "\n".join(f"  - {c}" for c in concepts)
        )
    else:
        concept_section = (
            "\nNo specific concepts were pre-detected. Please identify"
            f" any {capitalized} patterns or idioms present."
        )

    return (
        f"You are a programming teacher specializing in {capitalized}."
        " Analyze the following code component and create a"
        " language-specific lesson.\n\n"
        f"Component: {node.name}\n"
        f"Type: {node.type.value}\n"
        f"File: {node.file_path or 'N/A'}\n"
        f"Summary: {node.summary}\n"
        f"Tags: {', '.join(node.tags)}\n\n"
        f"Relationships:\n{relationships}\n"
        f"{concept_section}\n\n"
        "Return a JSON object with the following fields:\n"
        '- "languageNotes": A concise explanation of the'
        f" {capitalized}-specific patterns and idioms used in this"
        " component.\n"
        '- "concepts": An array of objects, each with:\n'
        '  - "name": The concept name (e.g., "async/await", "generics").\n'
        '  - "explanation": A beginner-friendly explanation of this concept'
        " as it applies to this component.\n\n"
        "Respond ONLY with the JSON object, no additional text."
    )


# ===========================================================================
# LLM response parsing
# ===========================================================================


def _extract_json(response: str) -> str:
    """Extract a JSON block from an LLM response."""
    fence_match = re.search(
        r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", response
    )
    if fence_match:
        return fence_match.group(1).strip()

    object_match = re.search(r"\{[\s\S]*\}", response)
    if object_match:
        return object_match.group(0).strip()

    return response.strip()


def parse_language_lesson_response(
    response: str,
) -> dict[str, Any]:
    """Parse an LLM response for language lesson content.

    Returns a dict with ``languageNotes`` and ``concepts`` keys.
    On parse failure, returns safe defaults.
    """
    try:
        json_str = _extract_json(response)
        parsed = json.loads(json_str)

        language_notes = (
            parsed["languageNotes"]
            if isinstance(parsed.get("languageNotes"), str)
            else ""
        )

        raw_concepts = parsed.get("concepts", [])
        concepts: list[dict[str, str]] = []
        if isinstance(raw_concepts, list):
            concepts.extend(
                {"name": c["name"], "explanation": c["explanation"]}
                for c in raw_concepts
                if (
                    isinstance(c, dict)
                    and isinstance(c.get("name"), str)
                    and isinstance(c.get("explanation"), str)
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"languageNotes": "", "concepts": []}
    else:
        return {"languageNotes": language_notes, "concepts": concepts}
