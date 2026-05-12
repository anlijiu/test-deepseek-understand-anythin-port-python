"""TOML parser tests — ported from toml-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.toml_config import TOMLParser


class TestTOMLParser:
    """Tests for TOMLParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = TOMLParser()
        assert parser.name == "toml-parser"
        assert parser.languages == ["toml"]

    def test_extracts_sections(self):
        """Extract [section] and [[array]] headers."""
        content = """[project]
name = "my-project"
version = "1.0.0"

[[dependencies]]
name = "requests"

[[dependencies]]
name = "flask"

[tool.poetry]
name = "poetry-test"
"""
        parser = TOMLParser()
        result = parser.analyze_file("pyproject.toml", content)

        assert len(result.sections) == 4

    def test_section_nesting_levels(self):
        """Dotted keys compute nesting level (e.g., [tool.poetry] = level 2)."""
        content = """[project]
name = "test"

[tool.poetry]
name = "poetry"

[tool.poetry.dependencies]
python = ">=3.11"
"""
        parser = TOMLParser()
        result = parser.analyze_file("test.toml", content)

        assert len(result.sections) == 3
        assert result.sections[0].level == 1  # [project]
        assert result.sections[1].level == 2  # [tool.poetry]
        assert result.sections[2].level == 3  # [tool.poetry.dependencies]

    def test_array_of_tables_sections(self):
        """[[array-of-tables]] headers are extracted with brackets preserved."""
        content = """[[products]]
name = "Hammer"

[[products]]
name = "Nail"
"""
        parser = TOMLParser()
        result = parser.analyze_file("test.toml", content)

        assert len(result.sections) == 2
        assert result.sections[0].name == "[[products]]"

    def test_section_line_ranges(self):
        """Line ranges extend to next section or EOF."""
        content = """[section-a]
key = "val"

[section-b]
key = "val"
"""
        parser = TOMLParser()
        result = parser.analyze_file("test.toml", content)

        assert len(result.sections) == 2
        for s in result.sections:
            assert s.line_range[1] >= s.line_range[0]

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = TOMLParser()
        result = parser.analyze_file("test.toml", "[section]\nkey = 1")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
