"""YAML config parser tests — ported from yaml-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.yaml_config import YAMLConfigParser


class TestYAMLConfigParser:
    """Tests for YAMLConfigParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs for YAML variants."""
        parser = YAMLConfigParser()
        assert parser.name == "yaml-config-parser"
        assert "yaml" in parser.languages
        assert "kubernetes" in parser.languages
        assert "docker-compose" in parser.languages
        assert "github-actions" in parser.languages
        assert "openapi" in parser.languages

    def test_extracts_top_level_keys_as_sections(self):
        """Extract top-level YAML keys as level-1 sections."""
        content = """name: my-app
version: "1.0.0"
dependencies:
  - flask
  - requests
"""
        parser = YAMLConfigParser()
        result = parser.analyze_file("config.yaml", content)

        assert len(result.sections) == 3
        section_names = [s.name for s in result.sections]
        assert "name" in section_names
        assert "version" in section_names
        assert "dependencies" in section_names
        for s in result.sections:
            assert s.level == 1

    def test_section_line_ranges_are_correct(self):
        """Line ranges extend to next section or EOF."""
        content = """name: app
version: "1"
description: test
"""
        parser = YAMLConfigParser()
        result = parser.analyze_file("test.yaml", content)

        assert len(result.sections) == 3
        # Each section should have valid range
        for s in result.sections:
            assert s.line_range[1] >= s.line_range[0]
        # Last section extends to EOF
        assert result.sections[-1].line_range[1] == 4

    def test_handles_array_root_yaml(self):
        """Array-root YAML (CloudFormation, K8s lists) — one section per entry."""
        content = """- name: service-a
  image: nginx
- name: service-b
  image: redis
- id: unnamed-item"""
        parser = YAMLConfigParser()
        result = parser.analyze_file("list.yaml", content)

        assert len(result.sections) == 3
        assert result.sections[0].name == "service-a"
        assert result.sections[1].name == "service-b"
        assert result.sections[2].name == "unnamed-item"

    def test_falls_back_to_regex_on_malformed_yaml(self):
        """When YAML parsing fails, falls back to regex extraction."""
        content = """key1: value
key2: <<: *invalid-anchor
"""
        parser = YAMLConfigParser()
        result = parser.analyze_file("broken.yaml", content)

        # Should still extract keys via regex
        assert len(result.sections) > 0

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = YAMLConfigParser()
        result = parser.analyze_file("test.yaml", "key: value")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
