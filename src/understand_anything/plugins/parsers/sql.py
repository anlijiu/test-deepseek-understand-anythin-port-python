"""SQL parser — extracts table, view, and index definitions.

Python port of the TypeScript ``SQLParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import DefinitionInfo, StructuralAnalysis


class SQLParser(AnalyzerPlugin):
    """Parses SQL files to extract table, view, and index definitions.

    Handles ``CREATE TABLE``, ``CREATE VIEW``, ``CREATE INDEX`` with
    ``IF NOT EXISTS`` and ``OR REPLACE`` variants.  Does not handle stored
    procedures, triggers, or schema-qualified names.
    """

    name = "sql-parser"
    languages: ClassVar[list[str]] = ["sql"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract database object definitions from SQL content.

        Args:
            file_path: Path to the SQL file (unused).
            content: Full text content of the SQL file.

        Returns:
            StructuralAnalysis with definitions populated.
        """
        return StructuralAnalysis(definitions=self._extract_definitions(content))

    # Regex patterns
    _TABLE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`|\")?(\w+)(?:`|\")?", re.IGNORECASE
    )
    _VIEW_RE = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:`|\")?(\w+)(?:`|\")?", re.IGNORECASE
    )
    _INDEX_RE = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`|\")?(\w+)(?:`|\")?", re.IGNORECASE
    )
    _CONSTRAINT_RE = re.compile(
        r"^\s*(PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT|INDEX|KEY)\s", re.IGNORECASE
    )

    def _extract_definitions(self, content: str) -> list[DefinitionInfo]:
        """Extract table, view, and index definitions from SQL content.

        Args:
            content: Full SQL text.

        Returns:
            List of ``DefinitionInfo`` for tables, views, and indexes.
        """
        definitions: list[DefinitionInfo] = []

        # CREATE TABLE
        for m in self._TABLE_RE.finditer(content):
            table_name = m.group(1)
            start_line = content[: m.start()].count("\n") + 1
            fields = self._extract_columns(content, m.start())
            after = content[m.start() :]
            end_paren = after.find(");")
            end_line = (
                content[: m.start() + end_paren + 2].count("\n") + 1
                if end_paren != -1
                else start_line + 5
            )
            definitions.append(
                DefinitionInfo(
                    name=table_name,
                    kind="table",
                    line_range=(start_line, end_line),
                    fields=fields,
                )
            )

        # CREATE VIEW
        for m in self._VIEW_RE.finditer(content):
            start_line = content[: m.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    name=m.group(1),
                    kind="view",
                    line_range=(start_line, start_line),
                )
            )

        # CREATE INDEX
        for m in self._INDEX_RE.finditer(content):
            start_line = content[: m.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    name=m.group(1),
                    kind="index",
                    line_range=(start_line, start_line),
                )
            )

        return definitions

    def _extract_columns(self, content: str, start_idx: int) -> list[str]:
        """Extract column names from a CREATE TABLE parenthesized block.

        Args:
            content: Full SQL text.
            start_idx: Character index where the CREATE TABLE match starts.

        Returns:
            List of column name strings.
        """
        fields: list[str] = []
        after_create = content[start_idx:]
        open_paren = after_create.find("(")
        if open_paren == -1:
            return fields
        close_paren = after_create.find(");", open_paren)
        if close_paren == -1:
            return fields

        body = after_create[open_paren + 1 : close_paren]
        for part in body.split(","):
            trimmed = part.strip()
            if self._CONSTRAINT_RE.match(trimmed):
                continue
            col_m = re.match(r"^(?:`|\")?(\w+)(?:`|\")?\s+", trimmed)
            if col_m:
                fields.append(col_m.group(1))
        return fields
