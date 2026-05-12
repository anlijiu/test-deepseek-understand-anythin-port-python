"""JSON/JSONC config parser — extracts top-level key sections and $ref references.

Python port of the TypeScript ``JSONConfigParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import (
    ReferenceResolution,
    SectionInfo,
    StructuralAnalysis,
)


def strip_jsonc_syntax(content: str) -> str:
    """Strip JSONC syntax (comments, trailing commas) for standard JSON parsing.

    Preserves string contents verbatim — comment-like sequences inside strings
    are not removed.

    Args:
        content: Raw JSONC source text.

    Returns:
        Valid JSON string with comments and trailing commas removed.
    """
    out: list[str] = []
    i = 0
    n = len(content)

    while i < n:
        ch = content[i]

        # String literal — copy verbatim, honoring escape sequences
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                c = content[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    i += 1
                    out.append(content[i])
                    i += 1
                    continue
                i += 1
                if c == '"':
                    break
            continue

        # Line comment
        if ch == "/" and i + 1 < n and content[i + 1] == "/":
            i += 2
            while i < n and content[i] != "\n":
                i += 1
            continue

        # Block comment
        if ch == "/" and i + 1 < n and content[i + 1] == "*":
            i += 2
            while i < n and not (
                content[i] == "*" and i + 1 < n and content[i + 1] == "/"
            ):
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1

    # Remove trailing commas before } or ] (allowing whitespace between)
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


class JSONConfigParser(AnalyzerPlugin):
    """Parses JSON / JSONC configuration files to extract top-level key sections
    and ``$ref`` references.

    Handles ``package.json``, ``tsconfig.json``, ``wrangler.jsonc``, JSON Schema,
    and OpenAPI spec files.  Does not descend into nested object structures
    beyond top-level keys.

    JSONC support: line comments, block comments, and trailing commas are
    stripped before ``JSON.parse``.  Strings are preserved.
    """

    name = "json-config-parser"
    languages: ClassVar[list[str]] = ["json", "jsonc", "json-schema", "openapi"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract top-level key sections from JSON/JSONC content.

        Args:
            file_path: Path to the JSON file (unused).
            content: Full text content of the JSON/JSONC file.

        Returns:
            StructuralAnalysis with sections populated.
        """
        return StructuralAnalysis(sections=self._extract_sections(content))

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution]:
        """Extract ``$ref`` references from JSON Schema / OpenAPI content.

        Args:
            file_path: Path to the source JSON file.
            content: Full text content of the JSON file.

        Returns:
            List of ``ReferenceResolution`` for external schema references.
        """
        refs: list[ReferenceResolution] = []
        for m in re.finditer(r'"\$ref"\s*:\s*"([^"]+)"', content):
            target = m.group(1)
            if target.startswith("#"):
                continue  # Skip internal refs
            line = content[: m.start()].count("\n") + 1
            refs.append(
                ReferenceResolution(
                    source=file_path,
                    target=target,
                    reference_type="schema",
                    line=line,
                )
            )
        return refs

    def _extract_sections(self, content: str) -> list[SectionInfo]:
        """Extract top-level keys as level-1 sections.

        Args:
            content: Full JSON/JSONC text.

        Returns:
            List of ``SectionInfo``, one per top-level key.
        """
        sections: list[SectionInfo] = []
        try:
            doc = json.loads(strip_jsonc_syntax(content))
            if isinstance(doc, dict):
                lines = content.split("\n")
                for key in doc:
                    escaped_key = json.dumps(key)
                    line_idx = -1
                    for idx, ln in enumerate(lines):
                        if escaped_key in ln:
                            line_idx = idx
                            break
                    if line_idx != -1:
                        sections.append(
                            SectionInfo(
                                name=key,
                                level=1,
                                line_range=(line_idx + 1, line_idx + 1),
                            )
                        )
                # Fix line_range end
                for i in range(len(sections)):
                    nxt = sections[i + 1] if i + 1 < len(sections) else None
                    start = sections[i].line_range[0]
                    end = nxt.line_range[0] - 1 if nxt else len(lines)
                    sections[i].line_range = (start, end)
        except (json.JSONDecodeError, Exception) as err:
            logging.warning("[json-parser] Failed to parse JSON: %s", err)
        return sections
