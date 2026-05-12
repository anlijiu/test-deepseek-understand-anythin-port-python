"""Shell parser — extracts function definitions and source references.

Python port of the TypeScript ``ShellParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import (
    FunctionInfo,
    ReferenceResolution,
    StructuralAnalysis,
)


class ShellParser(AnalyzerPlugin):
    """Parses shell scripts (``.sh``, ``.bash``) to extract function definitions
    and ``source`` references.

    Handles both ``name() {`` and ``function name {`` styles, including brace
    on next line.  Does not extract variable declarations, aliases, or trap
    handlers.
    """

    name = "shell-parser"
    languages: ClassVar[list[str]] = ["shell", "jenkinsfile"]

    # Match: name() {? or function name {? (brace optional on this line)
    _FUNC_RE = re.compile(
        r"^(?:function\s+)?(\w+)\s*\(\s*\)\s*\{?"
    )
    _FUNC_KW_RE = re.compile(r"^function\s+(\w+)\s*\{?")

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract function definitions from a shell script.

        Args:
            file_path: Path to the shell script (unused).
            content: Full text content of the shell script.

        Returns:
            StructuralAnalysis with functions populated.
        """
        return StructuralAnalysis(functions=self._extract_functions(content))

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution]:
        """Extract ``source`` / ``.`` references to other files.

        Args:
            file_path: Path to the source shell script.
            content: Full text content of the shell script.

        Returns:
            List of ``ReferenceResolution`` for sourced files.
        """
        refs: list[ReferenceResolution] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = re.match(r'^\s*(?:source|\.)[ \t]+["\']?([^"\'\s]+)', line)
            if m:
                refs.append(
                    ReferenceResolution(
                        source=file_path,
                        target=m.group(1),
                        reference_type="file",
                        line=i + 1,
                    )
                )
        return refs

    def _extract_functions(self, content: str) -> list[FunctionInfo]:
        """Extract shell function definitions.

        Args:
            content: Full shell script text.

        Returns:
            List of ``FunctionInfo`` for each function found.
        """
        functions: list[FunctionInfo] = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            m = self._FUNC_RE.match(line) or self._FUNC_KW_RE.match(line)
            if not m:
                continue

            name = m.group(1)
            has_brace_here = "{" in line
            # Find next non-blank line
            next_non_blank = i + 1
            while next_non_blank < len(lines) and lines[next_non_blank].strip() == "":
                next_non_blank += 1
            has_brace_next = (
                next_non_blank < len(lines)
                and lines[next_non_blank].strip().startswith("{")
            )

            if not has_brace_here and not has_brace_next:
                continue

            # Find closing brace
            start_brace_line = i if has_brace_here else next_non_blank
            depth = 0
            end_line = start_brace_line
            for j in range(start_brace_line, len(lines)):
                for ch in lines[j]:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth == 0:
                    end_line = j
                    break

            functions.append(
                FunctionInfo(
                    name=name,
                    line_range=(i + 1, end_line + 1),
                    params=[],
                )
            )

        return functions
