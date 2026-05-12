"""Dockerfile parser tests — ported from dockerfile-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.dockerfile import DockerfileParser


class TestDockerfileParser:
    """Tests for DockerfileParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = DockerfileParser()
        assert parser.name == "dockerfile-parser"
        assert parser.languages == ["dockerfile"]

    def test_extracts_single_stage(self):
        """Extract a single-stage Dockerfile service."""
        content = """FROM python:3.11-slim
WORKDIR /app
COPY . .
EXPOSE 8080
CMD ["python", "app.py"]
"""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", content)

        assert len(result.services) == 1
        assert result.services[0].name == "python"
        assert result.services[0].image == "python:3.11-slim"
        assert 8080 in result.services[0].ports

    def test_extracts_multi_stage_builds(self):
        """Extract multi-stage Dockerfile with named stages."""
        content = """FROM golang:1.21 AS builder
WORKDIR /build
RUN go build -o app

FROM alpine:3.19
COPY --from=builder /build/app /app
EXPOSE 3000
CMD ["/app"]
"""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", content)

        assert len(result.services) == 2
        assert result.services[0].name == "builder"
        assert result.services[0].image == "golang:1.21"
        assert result.services[1].name == "alpine"
        assert result.services[1].image == "alpine:3.19"
        assert 3000 in result.services[1].ports

    def test_extracts_expose_ports(self):
        """EXPOSE directives are parsed as ports within stage."""
        content = """FROM nginx:latest
EXPOSE 80 443
"""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", content)

        assert len(result.services) == 1
        assert 80 in result.services[0].ports
        assert 443 in result.services[0].ports

    def test_extracts_steps(self):
        """Dockerfile instructions are extracted as steps."""
        content = """FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
"""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", content)

        assert len(result.steps) >= 5
        step_names = [s.name for s in result.steps]
        assert any("FROM" in name for name in step_names)
        assert any("WORKDIR" in name for name in step_names)
        assert any("RUN" in name for name in step_names)
        assert any("CMD" in name for name in step_names)

    def test_stage_line_ranges_are_correct(self):
        """Each stage has correct line range bounds."""
        content = """FROM node:18 AS build
RUN npm install

FROM nginx:alpine
COPY --from=build /dist /usr/share/nginx/html
"""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", content)

        assert len(result.services) == 2
        assert result.services[0].line_range is not None
        assert result.services[1].line_range is not None
        assert result.services[0].line_range[0] < result.services[1].line_range[0]

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = DockerfileParser()
        result = parser.analyze_file("Dockerfile", "FROM alpine")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
