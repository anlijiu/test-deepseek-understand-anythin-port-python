"""Dockerfile parser — extracts multi-stage builds, ports, and steps.

Python port of the TypeScript ``DockerfileParser`` from
``@understand-anything/core``.
"""

from __future__ import annotations

import contextlib
import re
from typing import ClassVar

from understand_anything.plugins.extractors.types import AnalyzerPlugin
from understand_anything.types import ServiceInfo, StepInfo, StructuralAnalysis


class DockerfileParser(AnalyzerPlugin):
    """Parses Dockerfiles to extract multi-stage build stages, ``EXPOSE`` ports,
    and instruction steps.

    Associates ``EXPOSE`` ports with the correct stage based on ``FROM``
    directive ordering.  Does not parse ``ARG``/``ENV`` variable substitution
    or heredoc syntax.
    """

    name = "dockerfile-parser"
    languages: ClassVar[list[str]] = ["dockerfile"]

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Extract stages, ports, and steps from a Dockerfile.

        Args:
            file_path: Path to the Dockerfile (unused).
            content: Full text content of the Dockerfile.

        Returns:
            StructuralAnalysis with services and steps populated.
        """
        return StructuralAnalysis(
            services=self._extract_stages(content),
            steps=self._extract_steps(content),
        )

    def _extract_stages(self, content: str) -> list[ServiceInfo]:
        """Extract multi-stage build stages with ports.

        Args:
            content: Full Dockerfile text.

        Returns:
            List of ``ServiceInfo``, one per ``FROM`` stage.
        """
        stages: list[ServiceInfo] = []
        lines = content.split("\n")

        # First pass: find FROM line indices
        from_lines: list[int] = []
        for i, line in enumerate(lines):
            if re.match(r"^FROM\s+", line, re.IGNORECASE):
                from_lines.append(i)

        # Second pass: for each stage, collect EXPOSE ports within its range
        for s in range(len(from_lines)):
            stage_start = from_lines[s]
            stage_end = (
                from_lines[s + 1] - 1
                if s + 1 < len(from_lines)
                else len(lines) - 1
            )

            from_match = re.match(
                r"^FROM\s+(\S+)(?:\s+[Aa][Ss]\s+(\S+))?",
                lines[stage_start],
                re.IGNORECASE,
            )
            if not from_match:
                continue

            image = from_match.group(1)
            name = from_match.group(2) or image.split(":")[0].split("/")[-1]

            # Collect EXPOSE ports within this stage's range
            ports: list[int] = []
            for i in range(stage_start, stage_end + 1):
                expose_match = re.match(
                    r"^EXPOSE\s+(.+)", lines[i], re.IGNORECASE
                )
                if expose_match:
                    for p in expose_match.group(1).split():
                        with contextlib.suppress(ValueError):
                            ports.append(int(p))

            stages.append(
                ServiceInfo(
                    name=name,
                    image=image,
                    ports=ports,
                    line_range=(stage_start + 1, stage_end + 1),
                )
            )

        return stages

    _DOCKERFILE_INSTRUCTIONS = re.compile(
        r"^(FROM|RUN|COPY|ADD|WORKDIR|CMD|ENTRYPOINT|"
        r"ENV|ARG|EXPOSE|VOLUME|USER|HEALTHCHECK)\s",
        re.IGNORECASE,
    )

    def _extract_steps(self, content: str) -> list[StepInfo]:
        """Extract Dockerfile instructions as pipeline steps.

        Args:
            content: Full Dockerfile text.

        Returns:
            List of ``StepInfo``, one per instruction line.
        """
        steps: list[StepInfo] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = self._DOCKERFILE_INSTRUCTIONS.match(line)
            if m:
                instr = m.group(1).upper()
                rest = line[m.end() :].strip()[:60]
                steps.append(
                    StepInfo(
                        name=f"{instr} {rest}".strip(),
                        line_range=(i + 1, i + 1),
                    )
                )
        return steps
