"""Protobuf parser — extracts message, enum, and service definitions.

Python port of the TypeScript ``ProtobufParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import DefinitionInfo, EndpointInfo, StructuralAnalysis


class ProtobufParser(AnalyzerPlugin):
    """Parses Protocol Buffer (``.proto``) files to extract message, enum, and
    service definitions.

    Extracts message fields, enum values, and service RPC method endpoints.
    Does not handle nested message types, ``oneof`` fields, or proto2 extensions.
    """

    name = "protobuf-parser"
    languages: ClassVar[list[str]] = ["protobuf"]

    _MESSAGE_RE = re.compile(r"^message\s+(\w+)\s*\{", re.MULTILINE)
    _ENUM_RE = re.compile(r"^enum\s+(\w+)\s*\{", re.MULTILINE)
    _SERVICE_RE = re.compile(r"^service\s+(\w+)\s*\{", re.MULTILINE)
    _RPC_RE = re.compile(r"rpc\s+(\w+)\s*\(")
    _FIELD_RE = re.compile(
        r"^\s*(?:repeated\s+|optional\s+|required\s+)?"
        r"(?:map<[^>]+>\s+|\w+\s+)"
        r"(\w+)\s*=",
        re.MULTILINE,
    )
    _VALUE_RE = re.compile(r"^\s*(\w+)\s*=", re.MULTILINE)

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract message, enum, service definitions from a .proto file.

        Args:
            file_path: Path to the .proto file (unused).
            content: Full text content of the .proto file.

        Returns:
            StructuralAnalysis with definitions and endpoints populated.
        """
        return StructuralAnalysis(
            definitions=self._extract_definitions(content),
            endpoints=self._extract_service_methods(content),
        )

    def _extract_definitions(self, content: str) -> list[DefinitionInfo]:
        """Extract message and enum definitions.

        Args:
            content: Full .proto text.

        Returns:
            List of ``DefinitionInfo`` for messages and enums.
        """
        definitions: list[DefinitionInfo] = []

        # Messages
        for m in self._MESSAGE_RE.finditer(content):
            start_line = content[: m.start()].count("\n") + 1
            fields = self._extract_message_fields(content, m.start())
            after = content[m.start() :]
            close_brace = self._find_closing_brace(after)
            end_line = content[: m.start() + close_brace + 1].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    name=m.group(1),
                    kind="message",
                    line_range=(start_line, end_line),
                    fields=fields,
                )
            )

        # Enums
        for m in self._ENUM_RE.finditer(content):
            start_line = content[: m.start()].count("\n") + 1
            fields = self._extract_enum_values(content, m.start())
            after = content[m.start() :]
            close_brace = self._find_closing_brace(after)
            end_line = content[: m.start() + close_brace + 1].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    name=m.group(1),
                    kind="enum",
                    line_range=(start_line, end_line),
                    fields=fields,
                )
            )

        return definitions

    def _extract_service_methods(self, content: str) -> list[EndpointInfo]:
        """Extract service RPC method endpoints.

        Args:
            content: Full .proto text.

        Returns:
            List of ``EndpointInfo`` for each RPC method.
        """
        endpoints: list[EndpointInfo] = []

        for m in self._SERVICE_RE.finditer(content):
            service_name = m.group(1)
            after_service = content[m.start() :]
            close_brace = self._find_closing_brace(after_service)
            body = after_service[len(m.group(0)) : close_brace]
            body_start_idx = m.start() + len(m.group(0))

            for rpc_m in self._RPC_RE.finditer(body):
                line_num = (
                    content[: body_start_idx + rpc_m.start()].count("\n") + 1
                )
                endpoints.append(
                    EndpointInfo(
                        method="rpc",
                        path=f"{service_name}.{rpc_m.group(1)}",
                        line_range=(line_num, line_num),
                    )
                )

        return endpoints

    def _extract_message_fields(self, content: str, start_idx: int) -> list[str]:
        """Extract field names from a message body.

        Args:
            content: Full .proto text.
            start_idx: Position where the message definition starts.

        Returns:
            List of field name strings.
        """
        after_msg = content[start_idx:]
        open_brace = after_msg.find("{")
        if open_brace == -1:
            return []
        close_brace = self._find_closing_brace(after_msg)
        body = after_msg[open_brace + 1 : close_brace]

        return [m.group(1) for m in self._FIELD_RE.finditer(body)]

    def _extract_enum_values(self, content: str, start_idx: int) -> list[str]:
        """Extract enum value names from an enum body.

        Args:
            content: Full .proto text.
            start_idx: Position where the enum definition starts.

        Returns:
            List of enum value name strings.
        """
        after_enum = content[start_idx:]
        open_brace = after_enum.find("{")
        if open_brace == -1:
            return []
        close_brace = self._find_closing_brace(after_enum)
        body = after_enum[open_brace + 1 : close_brace]

        return [m.group(1) for m in self._VALUE_RE.finditer(body)]

    @staticmethod
    def _find_closing_brace(content: str) -> int:
        """Find the closing brace matching the first opening brace.

        Args:
            content: Text starting after the current position.

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
                "[protobuf-parser] Unbalanced braces detected "
                "(depth=%d), results may be incomplete",
                depth,
            )
        return len(content)
