"""Shell parser tests — ported from shell-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.shell import ShellParser


class TestShellParser:
    """Tests for ShellParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = ShellParser()
        assert parser.name == "shell-parser"
        assert "shell" in parser.languages
        assert "jenkinsfile" in parser.languages

    def test_extracts_function_definitions_parentheses_style(self):
        """Extract function definitions using name() { syntax."""
        content = """hello() {
    echo "Hello, $1"
}

greet() {
    local name="$1"
    echo "Hi, $name"
}
"""
        parser = ShellParser()
        result = parser.analyze_file("script.sh", content)

        assert len(result.functions) == 2
        assert result.functions[0].name == "hello"
        assert result.functions[1].name == "greet"

    def test_extracts_function_definitions_function_keyword_style(self):
        """Extract function definitions using 'function name {' syntax."""
        content = """function build {
    make all
}

function deploy {
    scp app server:/opt/app
}
"""
        parser = ShellParser()
        result = parser.analyze_file("script.sh", content)

        assert len(result.functions) == 2
        assert result.functions[0].name == "build"
        assert result.functions[1].name == "deploy"

    def test_requires_opening_brace(self):
        """Only extract functions that have an opening brace."""
        content = """helper() {
    echo "valid function"
}

not_a_func()
echo "just a stray paren"
"""
        parser = ShellParser()
        result = parser.analyze_file("script.sh", content)

        # "not_a_func()" has no brace, should be skipped
        names = [f.name for f in result.functions]
        assert "helper" in names
        assert "not_a_func" not in names

    def test_function_line_ranges_are_correct(self):
        """Function line ranges cover the full body."""
        content = """hello() {
    echo "line 1"
    echo "line 2"
    echo "line 3"
}
"""
        parser = ShellParser()
        result = parser.analyze_file("script.sh", content)

        assert len(result.functions) == 1
        assert result.functions[0].name == "hello"
        assert result.functions[0].line_range[0] == 1
        assert result.functions[0].line_range[1] == 5

    def test_extracts_source_references(self):
        """Extract 'source' and '.' references to other files."""
        content = """source ./common.sh
. /etc/config
source "./lib/utils.sh"
echo "done"
"""
        parser = ShellParser()
        refs = parser.extract_references("script.sh", content)

        assert len(refs) == 3
        targets = [r.target for r in refs]
        assert "./common.sh" in targets
        assert "/etc/config" in targets
        assert "./lib/utils.sh" in targets
        assert all(r.reference_type == "file" for r in refs)

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields for non-functions are empty."""
        parser = ShellParser()
        result = parser.analyze_file("test.sh", 'hello() { echo hi; }')
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
