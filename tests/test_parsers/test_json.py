"""JSON config parser tests — ported from json-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.json_config import JSONConfigParser, strip_jsonc_syntax


class TestStripJsoncSyntax:
    """Tests for the jsonc comment-stripping utility."""

    def test_preserves_plain_json(self):
        """Plain JSON passes through unchanged."""
        content = '{"name": "test", "version": "1.0"}'
        assert strip_jsonc_syntax(content) == content

    def test_strips_line_comments(self):
        """Line comments (//...) are removed."""
        content = """{
  // This is a comment
  "name": "test"
}"""
        result = strip_jsonc_syntax(content)
        assert "// This is a comment" not in result
        assert '"name"' in result

    def test_strips_block_comments(self):
        """Block comments are removed."""
        content = """{
  /* Multi-line
     comment */
  "name": "test"
}"""
        result = strip_jsonc_syntax(content)
        assert "/*" not in result
        assert '"name"' in result

    def test_strips_trailing_commas(self):
        """Trailing commas before } or ] are removed."""
        content = """{
  "a": 1,
  "b": 2,
}"""
        result = strip_jsonc_syntax(content)
        # Should be valid JSON after stripping
        import json
        json.loads(result)

    def test_preserves_comments_inside_strings(self):
        """Comment-like sequences inside strings are preserved."""
        content = '{"url": "http://example.com", "desc": "/* not a comment */"}'
        result = strip_jsonc_syntax(content)
        assert "http://example.com" in result
        assert "/* not a comment */" in result


class TestJSONConfigParser:
    """Tests for JSONConfigParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = JSONConfigParser()
        assert parser.name == "json-config-parser"
        assert "json" in parser.languages
        assert "jsonc" in parser.languages
        assert "json-schema" in parser.languages
        assert "openapi" in parser.languages

    def test_extracts_top_level_keys_as_sections(self):
        """Extract top-level JSON keys as level-1 sections."""
        content = """{
  "name": "my-package",
  "version": "1.0.0",
  "scripts": {
    "test": "pytest"
  }
}"""
        parser = JSONConfigParser()
        result = parser.analyze_file("package.json", content)

        assert len(result.sections) == 3
        section_names = [s.name for s in result.sections]
        assert "name" in section_names
        assert "version" in section_names
        assert "scripts" in section_names
        for s in result.sections:
            assert s.level == 1

    def test_section_line_ranges_are_correct(self):
        """Line ranges extend to next section or EOF."""
        content = """{
  "name": "test",
  "version": "1"
}"""
        parser = JSONConfigParser()
        result = parser.analyze_file("test.json", content)

        assert len(result.sections) == 2
        for s in result.sections:
            assert s.line_range[1] >= s.line_range[0]

    def test_handles_jsonc_with_comments(self):
        """JSON with comments (jsonc) is handled."""
        content = """{
  // Configuration file
  "port": 8080,
  /** Database settings */
  "database": "postgres"
}"""
        parser = JSONConfigParser()
        result = parser.analyze_file("config.jsonc", content)

        assert len(result.sections) >= 1
        section_names = [s.name for s in result.sections]
        assert "port" in section_names

    def test_extracts_json_schema_refs(self):
        """Extract $ref references from JSON Schema / OpenAPI."""
        content = """{
  "$ref": "./definitions.json",
  "properties": {
    "name": {"$ref": "#/definitions/name"}
  }
}"""
        parser = JSONConfigParser()
        refs = parser.extract_references("schema.json", content)

        # $ref to internal # should be skipped
        external_refs = [r for r in refs if not r.target.startswith("#")]
        assert len(external_refs) >= 1
        assert external_refs[0].target == "./definitions.json"
        assert external_refs[0].reference_type == "schema"

    def test_handles_malformed_json(self):
        """Malformed JSON does not crash the parser."""
        parser = JSONConfigParser()
        result = parser.analyze_file("broken.json", "{not valid json}")
        assert result.sections == []

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = JSONConfigParser()
        result = parser.analyze_file("test.json", '{"key": "val"}')
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
