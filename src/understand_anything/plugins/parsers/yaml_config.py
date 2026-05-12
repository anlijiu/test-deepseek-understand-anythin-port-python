"""YAML config parser — extracts top-level key sections.

Python port of the TypeScript ``YAMLConfigParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

import yaml

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import SectionInfo, StructuralAnalysis


class YAMLConfigParser(AnalyzerPlugin):
    """Parses YAML configuration files to extract top-level key sections.

    Uses the ``pyyaml`` library for parsing with a regex fallback for
    malformed input.  Only extracts top-level keys; does not descend into
    nested structures.

    The ``languages`` array also lists YAML-flavored special formats
    (``docker-compose``, ``kubernetes``, ``github-actions``, ``openapi``)
    so files the language-registry tags with those ids don't fall through
    to the "no parser matched" branch and lose all structural extraction.
    """

    name = "yaml-config-parser"
    languages: ClassVar[list[str]] = [
        "yaml",
        "kubernetes",
        "docker-compose",
        "github-actions",
        "openapi",
    ]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract top-level key sections from YAML content.

        Args:
            file_path: Path to the YAML file (unused).
            content: Full text content of the YAML file.

        Returns:
            StructuralAnalysis with sections populated.
        """
        return StructuralAnalysis(sections=self._extract_sections(content))

    def _extract_sections(self, content: str) -> list[SectionInfo]:
        """Extract top-level keys as level-1 sections.

        Args:
            content: Full YAML text.

        Returns:
            List of ``SectionInfo``, one per top-level key or array entry.
        """
        sections: list[SectionInfo] = []
        try:
            doc: Any = yaml.safe_load(content)
            if isinstance(doc, dict):
                lines = content.split("\n")
                for key in doc:
                    key_str = str(key)
                    escaped = re.escape(key_str)
                    line_idx = -1
                    for idx, ln in enumerate(lines):
                        if re.match(rf'^["\']?{escaped}["\']?\s*:', ln):
                            line_idx = idx
                            break
                    if line_idx != -1:
                        sections.append(
                            SectionInfo(
                                name=key_str,
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

            elif isinstance(doc, list):
                # Array-root YAML (e.g. CloudFormation snippets, K8s List docs)
                lines = content.split("\n")
                for i, entry in enumerate(doc):
                    name = f"[{i}]"
                    if isinstance(entry, dict):
                        entry_any: Any = entry
                        entry_name = entry_any.get("name")
                        entry_id = entry_any.get("id")
                        entry_kind = entry_any.get("kind")
                        if isinstance(entry_name, str):
                            name = entry_name
                        elif isinstance(entry_id, str):
                            name = entry_id
                        elif isinstance(entry_kind, str):
                            name = entry_kind
                    sections.append(
                        SectionInfo(
                            name=name,
                            level=1,
                            line_range=(1, len(lines)),
                        )
                    )
        except Exception as err:
            logging.warning(
                "[yaml-parser] YAML parse failed, falling back to regex "
                "extraction: %s",
                err,
            )
            # Fall back to regex
            lines = content.split("\n")
            for i, line in enumerate(lines):
                m = re.match(r"^(\w[\w-]*)\s*:", line)
                if m:
                    sections.append(
                        SectionInfo(
                            name=m.group(1),
                            level=1,
                            line_range=(i + 1, i + 1),
                        )
                    )
            for i in range(len(sections)):
                nxt = sections[i + 1] if i + 1 < len(sections) else None
                start = sections[i].line_range[0]
                end = nxt.line_range[0] - 1 if nxt else len(lines)
                sections[i].line_range = (start, end)

        return sections
