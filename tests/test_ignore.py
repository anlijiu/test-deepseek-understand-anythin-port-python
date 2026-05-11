"""Tests for ignore filter — pathspec-based file exclusion."""

from __future__ import annotations

from pathlib import Path

import pathspec
import pytest

from understand_anything.ignore.filter import (
    DEFAULT_IGNORE_PATTERNS,
    filter_files,
    load_ignore_spec,
    should_ignore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a project directory with some dummy files."""
    root = tmp_path / "project"
    root.mkdir()
    for sub in ["src", "node_modules", "__pycache__", ".git"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "src" / "main.py").write_text("print('hi')")
    (root / "README.md").write_text("# Hello")
    (root / ".gitignore").write_text("secrets.env\n")
    (root / ".understandignore").write_text("generated/\n")
    return root


# ---------------------------------------------------------------------------
# Default patterns
# ---------------------------------------------------------------------------


class TestDefaultPatterns:
    def test_contains_common_ignore_patterns(self) -> None:
        assert ".git" in DEFAULT_IGNORE_PATTERNS
        assert "node_modules" in DEFAULT_IGNORE_PATTERNS
        assert "__pycache__" in DEFAULT_IGNORE_PATTERNS
        assert ".understand-anything" in DEFAULT_IGNORE_PATTERNS

    def test_contains_media_patterns(self) -> None:
        assert "*.png" in DEFAULT_IGNORE_PATTERNS
        assert "*.jpg" in DEFAULT_IGNORE_PATTERNS
        assert "*.mp4" in DEFAULT_IGNORE_PATTERNS

    def test_contains_archive_patterns(self) -> None:
        assert "*.zip" in DEFAULT_IGNORE_PATTERNS
        assert "*.tar" in DEFAULT_IGNORE_PATTERNS
        assert "*.gz" in DEFAULT_IGNORE_PATTERNS


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------


class TestLoadIgnoreSpec:
    def test_loads_default_patterns(self, tmp_path: Path) -> None:
        spec = load_ignore_spec(tmp_path, include_gitignore=False, include_understandignore=False)
        assert spec.match_file("node_modules/foo.js")

    def test_loads_gitignore(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root, include_understandignore=False)
        assert spec.match_file("secrets.env")

    def test_loads_understandignore(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root, include_gitignore=False)
        assert spec.match_file("generated/stuff.py")

    def test_loads_both(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert spec.match_file("secrets.env")
        assert spec.match_file("generated/stuff.py")
        assert spec.match_file("node_modules/foo.js")

    def test_missing_files_no_error(self, tmp_path: Path) -> None:
        spec = load_ignore_spec(tmp_path)  # no .gitignore or .understandignore
        assert isinstance(spec, pathspec.PathSpec)


# ---------------------------------------------------------------------------
# should_ignore
# ---------------------------------------------------------------------------


class TestShouldIgnore:
    def test_ignores_node_modules(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert should_ignore(project_root / "node_modules" / "foo.js", spec,
                             project_root=project_root)

    def test_ignores_pycache(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert should_ignore(project_root / "__pycache__" / "module.pyc", spec,
                             project_root=project_root)

    def test_does_not_ignore_source_files(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert not should_ignore(project_root / "src" / "main.py", spec,
                                 project_root=project_root)

    def test_ignores_gitignore_pattern(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert should_ignore(project_root / "secrets.env", spec,
                             project_root=project_root)

    def test_ignores_understandignore_pattern(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert should_ignore(project_root / "generated" / "data.json", spec,
                             project_root=project_root)

    def test_without_project_root(self, tmp_path: Path) -> None:
        spec = load_ignore_spec(tmp_path, include_gitignore=False, include_understandignore=False)
        assert should_ignore(tmp_path / "node_modules" / "x.js", spec)

    def test_negation_pattern(self, tmp_path: Path) -> None:
        # ! patterns in .understandignore override earlier rules
        (tmp_path / ".understandignore").write_text("!important.txt\n")
        spec = load_ignore_spec(tmp_path, include_gitignore=False)
        # pathspec handles negation natively
        assert not spec.match_file("important.txt")


# ---------------------------------------------------------------------------
# filter_files
# ---------------------------------------------------------------------------


class TestFilterFiles:
    def test_filters_out_ignored(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        paths = [
            project_root / "src" / "main.py",
            project_root / "node_modules" / "lib.js",
            project_root / "README.md",
        ]
        filtered = filter_files(paths, spec, project_root=project_root)
        assert len(filtered) == 2
        assert project_root / "node_modules" / "lib.js" not in filtered

    def test_empty_list(self, project_root: Path) -> None:
        spec = load_ignore_spec(project_root)
        assert filter_files([], spec) == []
