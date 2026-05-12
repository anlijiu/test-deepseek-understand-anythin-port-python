"""Makefile parser tests — ported from makefile-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.makefile import MakefileParser


class TestMakefileParser:
    """Tests for MakefileParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = MakefileParser()
        assert parser.name == "makefile-parser"
        assert parser.languages == ["makefile"]

    def test_extracts_targets_as_steps(self):
        """Extract Makefile targets as steps."""
        content = """build:
\tgcc -o program main.c

clean:
\trm -f program *.o

test:
\t./run_tests.sh
"""
        parser = MakefileParser()
        result = parser.analyze_file("Makefile", content)

        assert len(result.steps) == 3
        names = [s.name for s in result.steps]
        assert "build" in names
        assert "clean" in names
        assert "test" in names

    def test_skips_special_dot_targets(self):
        """Special targets starting with '.' are skipped."""
        content = """.PHONY: all clean

all: build test

build:
\tgcc -o app main.c

.DEFAULT:
\techo default
"""
        parser = MakefileParser()
        result = parser.analyze_file("Makefile", content)

        names = [s.name for s in result.steps]
        assert ".PHONY" not in names
        assert ".DEFAULT" not in names
        assert "all" in names
        assert "build" in names

    def test_skips_variable_assignments(self):
        """Variable assignments (:=, ?=) are not treated as targets."""
        content = """CC := gcc
CFLAGS := -Wall -O2

build:
\t$(CC) $(CFLAGS) -o app main.c
"""
        parser = MakefileParser()
        result = parser.analyze_file("Makefile", content)

        names = [s.name for s in result.steps]
        assert "CC" not in names
        assert "CFLAGS" not in names
        assert "build" in names

    def test_target_line_ranges_include_recipe(self):
        """Target line range extends to include recipe lines."""
        content = """build:
\tgcc -c main.c
\tgcc -c utils.c
\tgcc -o app main.o utils.o

clean:
\trm -f *.o app
"""
        parser = MakefileParser()
        result = parser.analyze_file("Makefile", content)

        assert len(result.steps) == 2
        assert result.steps[0].name == "build"
        assert result.steps[0].line_range[1] >= result.steps[0].line_range[0]
        # build should span at least 4 lines (target + 3 recipe lines)
        assert result.steps[0].line_range[1] - result.steps[0].line_range[0] >= 2

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = MakefileParser()
        result = parser.analyze_file("Makefile", "all:\n\techo hi")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
