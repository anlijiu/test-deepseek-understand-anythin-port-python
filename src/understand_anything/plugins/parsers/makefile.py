"""Makefile parser — extracts build targets and their line ranges.

Python port of the TypeScript ``MakefileParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import StepInfo, StructuralAnalysis


class MakefileParser(AnalyzerPlugin):
    """Parses Makefiles to extract build targets and their line ranges.

    Filters out special Make targets (e.g. ``.PHONY``, ``.DEFAULT``,
    ``.SUFFIXES``) and variable assignments.  Does not parse target
    dependencies or recipe commands.
    """

    name = "makefile-parser"
    languages: ClassVar[list[str]] = ["makefile"]

    _TARGET_RE = re.compile(r"^([a-zA-Z_.][a-zA-Z0-9_.-]*)(?:\s+.*)?:")

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract Makefile targets as pipeline steps.

        Args:
            file_path: Path to the Makefile (unused).
            content: Full text content of the Makefile.

        Returns:
            StructuralAnalysis with steps populated.
        """
        return StructuralAnalysis(steps=self._extract_targets(content))

    def _extract_targets(self, content: str) -> list[StepInfo]:
        """Extract named targets from Makefile content.

        Args:
            content: Full Makefile text.

        Returns:
            List of ``StepInfo``, one per target.
        """
        targets: list[StepInfo] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = self._TARGET_RE.match(line)
            if m and ":=" not in line and "?=" not in line:
                name = m.group(1)
                # Skip special Make targets
                if name.startswith("."):
                    continue
                # Find end of target (next non-indented non-empty line or EOF)
                end_line = i + 1
                while end_line < len(lines):
                    next_line = lines[end_line]
                    if next_line == "" or next_line.startswith(("\t", "  ")):
                        end_line += 1
                    else:
                        break
                targets.append(
                    StepInfo(
                        name=name,
                        line_range=(i + 1, end_line),
                    )
                )
        return targets
