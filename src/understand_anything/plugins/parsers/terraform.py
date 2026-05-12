"""Terraform parser — extracts resource, variable, and output blocks.

Python port of the TypeScript ``TerraformParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import DefinitionInfo, ResourceInfo, StructuralAnalysis


class TerraformParser(AnalyzerPlugin):
    """Parses Terraform (``.tf``) files to extract resource, data, module,
    variable, and output blocks.

    Handles HCL block syntax with brace-matching for line range computation.
    Does not handle provider blocks, locals, or terraform configuration blocks.
    """

    name = "terraform-parser"
    languages: ClassVar[list[str]] = ["terraform"]

    _RESOURCE_RE = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
    _DATA_RE = re.compile(r'^data\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
    _MODULE_RE = re.compile(r'^module\s+"([^"]+)"\s*\{', re.MULTILINE)
    _VAR_RE = re.compile(r'^variable\s+"([^"]+)"\s*\{', re.MULTILINE)
    _OUTPUT_RE = re.compile(r'^output\s+"([^"]+)"\s*\{', re.MULTILINE)

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract resource, variable, and output blocks from a .tf file.

        Args:
            file_path: Path to the .tf file (unused).
            content: Full text content of the .tf file.

        Returns:
            StructuralAnalysis with resources and definitions populated.
        """
        return StructuralAnalysis(
            resources=self._extract_resources(content),
            definitions=self._extract_variables_and_outputs(content),
        )

    def _extract_resources(self, content: str) -> list[ResourceInfo]:
        """Extract resource, data, and module blocks.

        Args:
            content: Full .tf text.

        Returns:
            List of ``ResourceInfo`` for each block.
        """
        resources: list[ResourceInfo] = []

        patterns = [
            (self._RESOURCE_RE, lambda m: f"{m.group(1)}.{m.group(2)}", lambda m: m.group(1)),
            (self._DATA_RE, lambda m: f"data.{m.group(1)}.{m.group(2)}", lambda m: f"data.{m.group(1)}"),
            (self._MODULE_RE, lambda m: f"module.{m.group(1)}", lambda _: "module"),
        ]

        for pattern, name_fn, kind_fn in patterns:
            for m in pattern.finditer(content):
                start_line = content[: m.start()].count("\n") + 1
                after = content[m.start() :]
                close_brace = self._find_closing_brace(after)
                end_line = content[: m.start() + close_brace + 1].count("\n") + 1
                resources.append(
                    ResourceInfo(
                        name=name_fn(m),
                        kind=kind_fn(m),
                        line_range=(start_line, end_line),
                    )
                )

        return resources

    def _extract_variables_and_outputs(
        self, content: str
    ) -> list[DefinitionInfo]:
        """Extract variable and output block definitions.

        Args:
            content: Full .tf text.

        Returns:
            List of ``DefinitionInfo`` for variables and outputs.
        """
        definitions: list[DefinitionInfo] = []

        patterns = [
            (self._VAR_RE, "variable"),
            (self._OUTPUT_RE, "output"),
        ]

        for pattern, kind in patterns:
            for m in pattern.finditer(content):
                start_line = content[: m.start()].count("\n") + 1
                after = content[m.start() :]
                close_brace = self._find_closing_brace(after)
                end_line = content[: m.start() + close_brace + 1].count("\n") + 1
                definitions.append(
                    DefinitionInfo(
                        name=m.group(1),
                        kind=kind,
                        line_range=(start_line, end_line),
                    )
                )

        return definitions

    @staticmethod
    def _find_closing_brace(content: str) -> int:
        """Find the matching closing brace for the first opening brace.

        Args:
            content: Text starting at the current position.

        Returns:
            Index of the matching closing brace, or ``len(content)`` if
            unbalanced.
        """
        depth = 0
        for i, ch in enumerate(content):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        if depth != 0:
            logging.warning(
                "[terraform-parser] Unbalanced braces detected "
                "(depth=%d), results may be incomplete",
                depth,
            )
        return len(content)
