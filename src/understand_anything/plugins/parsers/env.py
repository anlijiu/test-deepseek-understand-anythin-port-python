""".env file parser — extracts environment variable definitions.

Python port of the TypeScript ``EnvParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import DefinitionInfo, StructuralAnalysis


class EnvParser(AnalyzerPlugin):
    """Parses ``.env`` files to extract environment variable definitions.

    Handles ``KEY=value`` syntax, skipping comments and empty lines.
    Does not handle ``export VAR=value`` syntax or multi-line values.
    """

    name = "env-parser"
    languages: ClassVar[list[str]] = ["env"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract environment variable definitions from .env content.

        Args:
            file_path: Path to the .env file (unused).
            content: Full text content of the .env file.

        Returns:
            StructuralAnalysis with definitions populated.
        """
        return StructuralAnalysis(definitions=self._extract_variables(content))

    def _extract_variables(self, content: str) -> list[DefinitionInfo]:
        """Extract variable definitions from .env content.

        Args:
            content: Full .env text.

        Returns:
            List of ``DefinitionInfo`` with kind ``"variable"``.
        """
        definitions: list[DefinitionInfo] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*?)=", stripped)
            if m:
                definitions.append(
                    DefinitionInfo(
                        name=m.group(1),
                        kind="variable",
                        line_range=(i + 1, i + 1),
                    )
                )
        return definitions
