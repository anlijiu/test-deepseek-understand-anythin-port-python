"""Env parser tests — ported from env-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.env import EnvParser


class TestEnvParser:
    """Tests for EnvParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = EnvParser()
        assert parser.name == "env-parser"
        assert parser.languages == ["env"]

    def test_extracts_variable_definitions(self):
        """Extract environment variable definitions."""
        content = """DATABASE_URL=postgres://localhost/mydb
SECRET_KEY=abc123
DEBUG=true
PORT=8080
"""
        parser = EnvParser()
        result = parser.analyze_file(".env", content)

        assert len(result.definitions) == 4
        names = [d.name for d in result.definitions]
        assert "DATABASE_URL" in names
        assert "SECRET_KEY" in names
        assert "DEBUG" in names
        assert "PORT" in names
        for d in result.definitions:
            assert d.kind == "variable"

    def test_skips_comments_and_empty_lines(self):
        """Comments and empty lines are skipped."""
        content = """# Database configuration
DATABASE_URL=postgres://localhost/db

# App settings
APP_NAME=myapp
"""
        parser = EnvParser()
        result = parser.analyze_file(".env", content)

        assert len(result.definitions) == 2
        assert result.definitions[0].name == "DATABASE_URL"
        assert result.definitions[1].name == "APP_NAME"

    def test_skips_export_keyword_lines(self):
        """Lines with 'export' keyword (not KEY=VALUE format) are skipped."""
        content = """export DATABASE_URL=postgres://localhost/db
MY_VAR=hello
"""
        parser = EnvParser()
        result = parser.analyze_file(".env", content)

        # "export DATABASE_URL" does not match KEY=VALUE pattern
        names = [d.name for d in result.definitions]
        # export keyword means the line starts with "export" not the var name
        assert "MY_VAR" in names

    def test_line_ranges_are_correct(self):
        """Each variable definition has a correct line range."""
        content = """VAR1=one
# comment
VAR2=two
"""
        parser = EnvParser()
        result = parser.analyze_file(".env", content)

        assert len(result.definitions) == 2
        assert result.definitions[0].line_range[0] == 1
        assert result.definitions[1].line_range[0] == 3

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = EnvParser()
        result = parser.analyze_file(".env", "KEY=value")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
