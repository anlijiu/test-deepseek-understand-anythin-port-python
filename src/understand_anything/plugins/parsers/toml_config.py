"""TOML config parser — extracts section headers.

Python port of the TypeScript ``TOMLParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import SectionInfo, StructuralAnalysis


class TOMLParser(AnalyzerPlugin):
    """Parses TOML files to extract section headers.

    Handles ``[section]`` and ``[[array-of-tables]]`` headers with nesting
    level computed from dotted key paths (e.g. ``[tool.poetry]`` = level 2).
    Does not parse individual key-value pairs within sections.
    """

    name = "toml-parser"
    languages: ClassVar[list[str]] = ["toml"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract section headers from TOML content.

        Args:
            file_path: Path to the TOML file (unused).
            content: Full text content of the TOML file.

        Returns:
            StructuralAnalysis with sections populated.
        """
        return StructuralAnalysis(sections=self._extract_sections(content))

    def _extract_sections(self, content: str) -> list[SectionInfo]:
        """Extract ``[section]`` and ``[[array]]`` headers.

        Args:
            content: Full TOML text.

        Returns:
            List of ``SectionInfo`` with computed nesting levels.
        """
        sections: list[SectionInfo] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = re.match(r"^\s*\[(\[?)([^\]]+)\]?\]", line)
            if m:
                is_array = m.group(1) == "["
                name = m.group(2).strip()
                sections.append(
                    SectionInfo(
                        name=f"[[{name}]]" if is_array else name,
                        level=name.count(".") + 1,
                        line_range=(i + 1, i + 1),
                    )
                )

        # Fix line_range end
        for i in range(len(sections)):
            nxt = sections[i + 1] if i + 1 < len(sections) else None
            start = sections[i].line_range[0]
            end = nxt.line_range[0] - 1 if nxt else len(lines)
            sections[i].line_range = (start, end)

        return sections
