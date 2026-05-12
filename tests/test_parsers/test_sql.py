"""SQL parser tests — ported from sql-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.sql import SQLParser


class TestSQLParser:
    """Tests for SQLParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = SQLParser()
        assert parser.name == "sql-parser"
        assert parser.languages == ["sql"]

    def test_extracts_create_table_definitions(self):
        """Extract CREATE TABLE statements with columns."""
        content = """CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE
);

CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    title TEXT,
    user_id INTEGER REFERENCES users(id)
);
"""
        parser = SQLParser()
        result = parser.analyze_file("schema.sql", content)

        tables = [d for d in result.definitions if d.kind == "table"]
        assert len(tables) == 2
        assert tables[0].name == "users"
        assert len(tables[0].fields) >= 2  # should have id, name columns
        assert "id" in tables[0].fields
        assert tables[1].name == "posts"
        assert len(tables[1].fields) >= 2

    def test_handles_if_not_exists(self):
        """CREATE TABLE IF NOT EXISTS variant."""
        content = """CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY,
    name TEXT
);
"""
        parser = SQLParser()
        result = parser.analyze_file("schema.sql", content)

        tables = [d for d in result.definitions if d.kind == "table"]
        assert len(tables) == 1
        assert tables[0].name == "migrations"

    def test_extracts_create_view(self):
        """Extract CREATE VIEW definitions."""
        content = """CREATE VIEW active_users AS
SELECT * FROM users WHERE active = true;

CREATE OR REPLACE VIEW report AS
SELECT * FROM data;
"""
        parser = SQLParser()
        result = parser.analyze_file("views.sql", content)

        views = [d for d in result.definitions if d.kind == "view"]
        assert len(views) == 2
        assert views[0].name == "active_users"
        assert views[1].name == "report"

    def test_extracts_create_index(self):
        """Extract CREATE INDEX definitions."""
        content = """CREATE INDEX idx_users_email ON users(email);
CREATE UNIQUE INDEX idx_unique_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_created ON orders(created_at);
"""
        parser = SQLParser()
        result = parser.analyze_file("indexes.sql", content)

        indexes = [d for d in result.definitions if d.kind == "index"]
        assert len(indexes) == 3
        assert indexes[0].name == "idx_users_email"
        assert indexes[1].name == "idx_unique_name"

    def test_skips_constraints_in_column_extraction(self):
        """Constraint keywords are not extracted as column names."""
        content = """CREATE TABLE example (
    id INTEGER PRIMARY KEY,
    name TEXT,
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
);
"""
        parser = SQLParser()
        result = parser.analyze_file("schema.sql", content)

        assert len(result.definitions) == 1
        # Should extract columns but skip CONSTRAINT line
        assert "id" in result.definitions[0].fields
        assert "name" in result.definitions[0].fields

    def test_line_ranges_are_correct(self):
        """Line ranges cover the full definition."""
        content = """CREATE TABLE t1 (
    col INTEGER
);

CREATE TABLE t2 (
    col TEXT
);
"""
        parser = SQLParser()
        result = parser.analyze_file("test.sql", content)

        assert len(result.definitions) >= 2
        for d in result.definitions:
            assert d.line_range[1] >= d.line_range[0]

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = SQLParser()
        result = parser.analyze_file("test.sql", "CREATE TABLE t (id INTEGER);")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
