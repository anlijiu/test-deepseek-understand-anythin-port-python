"""Markdown file parser — extracts heading sections and local file references.

Python port of the TypeScript ``MarkdownParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import (
    ReferenceResolution,
    SectionInfo,
    StructuralAnalysis,
)


class MarkdownParser(AnalyzerPlugin):
    """Parses Markdown files to extract heading sections and local file/image references.

    Supports ATX-style headings (``#`` through ``######``) with line range
    computation.  Does not extract code blocks, front matter fields, or
    external URL references.
    """

    name = "markdown-parser"
    languages: ClassVar[list[str]] = ["markdown"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract heading sections from a Markdown file.

        Args:
            file_path: Path to the markdown file (unused).
            content: Full text content of the markdown file.

        Returns:
            StructuralAnalysis with sections populated.
        """
        return StructuralAnalysis(sections=self._extract_sections(content))

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution]:
        """Extract local file and image references from Markdown links.

        Args:
            file_path: Path to the source markdown file.
            content: Full text content of the markdown file.

        Returns:
            List of ``ReferenceResolution`` for local file/image references.
        """
        refs: list[ReferenceResolution] = []
        for m in re.finditer(r"!?\[([^\]]*)\]\(([^)]+)\)", content):
            target = m.group(2)
            if target.startswith("http"):
                continue  # Skip external URLs
            line = content[: m.start()].count("\n") + 1
            refs.append(
                ReferenceResolution(
                    source=file_path,
                    target=target,
                    reference_type="image" if m.group(0).startswith("!") else "file",
                    line=line,
                )
            )
        return refs

    def _extract_sections(self, content: str) -> list[SectionInfo]:
        """Extract heading-based sections from markdown content.

        Args:
            content: Full markdown text.

        Returns:
            List of ``SectionInfo`` with corrected line ranges.
        """
        sections: list[SectionInfo] = []
        lines = content.split("\n")
        in_fence = False
        fence_marker: str | None = None

        for i, line in enumerate(lines):
            # Toggle fenced-code-block state
            fence_match = re.match(r"^(```+|~~~+)", line)
            if fence_match:
                if not in_fence:
                    in_fence = True
                    fence_marker = fence_match.group(1)[0]
                elif fence_marker and line.startswith(fence_marker):
                    in_fence = False
                    fence_marker = None
                continue
            if in_fence:
                continue

            m = re.match(r"^(#{1,6})\s+(.+)", line)
            if m:
                sections.append(
                    SectionInfo(
                        name=m.group(2).strip(),
                        level=len(m.group(1)),
                        line_range=(i + 1, i + 1),
                    )
                )

        # Fix line_range end for each section (extends to next heading or EOF)
        for i in range(len(sections)):
            nxt = sections[i + 1] if i + 1 < len(sections) else None
            start = sections[i].line_range[0]
            end = nxt.line_range[0] - 1 if nxt else len(lines)
            sections[i].line_range = (start, end)

        return sections
