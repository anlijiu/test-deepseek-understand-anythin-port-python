"""Tests for .understandignore generator."""

from __future__ import annotations

from pathlib import Path

from understand_anything.ignore.generator import (
    generate_understandignore,
    guess_ignore_rules,
)


class TestGuessIgnoreRules:
    def test_returns_language_patterns(self) -> None:
        rules = guess_ignore_rules(languages=["python"])
        assert "__pycache__" in rules
        assert "*.pyc" in rules
        assert ".venv" in rules

    def test_returns_framework_patterns(self) -> None:
        rules = guess_ignore_rules(frameworks=["django"])
        assert "*.sqlite3" in rules
        assert "staticfiles" in rules

    def test_combines_both(self) -> None:
        rules = guess_ignore_rules(languages=["python", "javascript"], frameworks=["react"])
        assert "__pycache__" in rules
        assert "node_modules" in rules
        assert "build" in rules  # from react

    def test_deduplicates(self) -> None:
        # "build" appears in both python and javascript
        rules = guess_ignore_rules(languages=["python", "javascript"])
        assert rules.count("build") == 1

    def test_includes_large_files(self) -> None:
        rules = guess_ignore_rules(large_files=["big_data.json", "dump.sql"])
        assert "big_data.json" in rules
        assert "dump.sql" in rules

    def test_empty_returns_empty_list(self) -> None:
        assert guess_ignore_rules() == []

    def test_sorted_output(self) -> None:
        rules = guess_ignore_rules(languages=["rust", "go"])
        assert rules == sorted(rules)

    def test_unknown_language_ignored_gracefully(self) -> None:
        rules = guess_ignore_rules(languages=["brainfuck"])
        assert rules == []


class TestGenerateUnderstandignore:
    def test_generates_file(self, tmp_path: Path) -> None:
        target = generate_understandignore(
            tmp_path,
            project_name="test-project",
            languages=["python"],
        )
        assert target.is_file()
        content = target.read_text()
        assert "test-project" in content
        assert "__pycache__" in content
        assert "*.pyc" in content

    def test_no_overwrite_by_default(self, tmp_path: Path) -> None:
        ui_path = tmp_path / ".understandignore"
        ui_path.write_text("original content")
        target = generate_understandignore(tmp_path, languages=["python"])
        assert target.read_text() == "original content"

    def test_overwrite_flag(self, tmp_path: Path) -> None:
        ui_path = tmp_path / ".understandignore"
        ui_path.write_text("original content")
        target = generate_understandignore(
            tmp_path, languages=["go"], overwrite=True
        )
        assert "vendor" in target.read_text()

    def test_empty_languages_produces_header_only(self, tmp_path: Path) -> None:
        target = generate_understandignore(tmp_path)
        content = target.read_text()
        assert content.strip().startswith("#")
        # No patterns, just header
        assert "__pycache__" not in content
