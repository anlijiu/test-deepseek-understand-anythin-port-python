"""Shared fixtures for understand-anything tests."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def python_language():
    """Tree-sitter Language for Python (session-scoped)."""
    import tree_sitter_python
    from tree_sitter import Language

    return Language(tree_sitter_python.language())  # type: ignore[deprecated]


@pytest.fixture(scope="session")
def python_parser(python_language):
    """Tree-sitter Parser configured for Python (session-scoped)."""
    from tree_sitter import Parser

    parser = Parser(python_language)
    return parser


@pytest.fixture
def parse_python(python_parser):
    """Parse Python source code string → root node."""

    def _parse(code: str) -> "tree_sitter.Node":  # type: ignore[name-defined]
        tree = python_parser.parse(bytes(code, "utf-8"))
        return tree.root_node

    return _parse
