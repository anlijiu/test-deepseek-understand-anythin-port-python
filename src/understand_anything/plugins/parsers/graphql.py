"""GraphQL schema parser — extracts type definitions and endpoint operations.

Python port of the TypeScript ``GraphQLParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import DefinitionInfo, EndpointInfo, StructuralAnalysis


class GraphQLParser(AnalyzerPlugin):
    """Parses GraphQL schema files to extract type definitions and endpoint
    operations (Query, Mutation, Subscription).

    Does not handle schema directives, fragments, or inline union members.
    """

    name = "graphql-parser"
    languages: ClassVar[list[str]] = ["graphql"]

    # Skip these type names — they are handled as endpoints instead
    _ENDPOINT_TYPES = frozenset({"Query", "Mutation", "Subscription"})

    _TYPE_RE = re.compile(
        r"^(type|input|enum|interface|union|scalar)\s+(\w+)", re.MULTILINE
    )

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract type definitions and endpoint operations from a GraphQL schema.

        Args:
            file_path: Path to the GraphQL file (unused).
            content: Full text content of the GraphQL schema.

        Returns:
            StructuralAnalysis with definitions and endpoints populated.
        """
        return StructuralAnalysis(
            definitions=self._extract_definitions(content),
            endpoints=self._extract_endpoints(content),
        )

    def _extract_definitions(self, content: str) -> list[DefinitionInfo]:
        """Extract type, input, enum, interface, union, and scalar definitions.

        Args:
            content: Full GraphQL schema text.

        Returns:
            List of ``DefinitionInfo`` for type definitions.
        """
        definitions: list[DefinitionInfo] = []

        for m in self._TYPE_RE.finditer(content):
            kind = m.group(1)
            name = m.group(2)
            if name in self._ENDPOINT_TYPES:
                continue
            start_line = content[: m.start()].count("\n") + 1
            fields = self._extract_fields(content, m.start())
            after = content[m.start() :]
            close_brace = after.find("}")
            end_line = (
                content[: m.start() + close_brace + 1].count("\n") + 1
                if close_brace != -1
                else start_line
            )
            definitions.append(
                DefinitionInfo(
                    name=name,
                    kind=kind,
                    line_range=(start_line, end_line),
                    fields=fields,
                )
            )

        return definitions

    def _extract_endpoints(self, content: str) -> list[EndpointInfo]:
        """Extract Query/Mutation/Subscription fields as endpoints.

        Args:
            content: Full GraphQL schema text.

        Returns:
            List of ``EndpointInfo`` for each operation field.
        """
        endpoints: list[EndpointInfo] = []
        block_re = re.compile(
            r"^(type)\s+(Query|Mutation|Subscription)\s*\{", re.MULTILINE
        )

        for m in block_re.finditer(content):
            method = m.group(2)
            start_idx = m.start() + len(m.group(0))

            # Find closing brace
            depth = 1
            i = start_idx
            while i < len(content) and depth > 0:
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                i += 1

            block_content = content[start_idx : i - 1]
            block_start_line = content[:start_idx].count("\n") + 1

            for j, line in enumerate(block_content.split("\n")):
                field_m = re.match(r"^(\w+)", line.strip())
                if field_m and field_m.group(1):
                    endpoints.append(
                        EndpointInfo(
                            method=method,
                            path=field_m.group(1),
                            line_range=(block_start_line + j, block_start_line + j),
                        )
                    )

        return endpoints

    def _extract_fields(self, content: str, start_idx: int) -> list[str]:
        """Extract field names from a GraphQL type body.

        Args:
            content: Full schema text.
            start_idx: Position where the type definition starts.

        Returns:
            List of field name strings.
        """
        fields: list[str] = []
        after_type = content[start_idx:]
        open_brace = after_type.find("{")
        if open_brace == -1:
            return fields

        depth = 1
        i = open_brace + 1
        while i < len(after_type) and depth > 0:
            if after_type[i] == "{":
                depth += 1
            elif after_type[i] == "}":
                depth -= 1
            i += 1

        body = after_type[open_brace + 1 : i - 1]
        for line in body.split("\n"):
            field_m = re.match(r"^(\w+)", line.strip())
            if field_m:
                fields.append(field_m.group(1))
        return fields
