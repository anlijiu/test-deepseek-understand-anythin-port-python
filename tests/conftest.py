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


@pytest.fixture(scope="session")
def cpp_language():
    """Tree-sitter Language for C/C++ (session-scoped)."""
    import tree_sitter_cpp
    from tree_sitter import Language

    return Language(tree_sitter_cpp.language())  # type: ignore[deprecated]


@pytest.fixture(scope="session")
def cpp_parser(cpp_language):
    """Tree-sitter Parser configured for C/C++ (session-scoped)."""
    from tree_sitter import Parser

    parser = Parser(cpp_language)
    return parser


@pytest.fixture
def parse_cpp(cpp_parser):
    """Parse C/C++ source code string → root node."""

    def _parse(code: str) -> "tree_sitter.Node":  # type: ignore[name-defined]
        tree = cpp_parser.parse(bytes(code, "utf-8"))
        return tree.root_node

    return _parse


@pytest.fixture(scope="session")
def typescript_language():
    """Tree-sitter Language for TypeScript (session-scoped)."""
    import tree_sitter_typescript
    from tree_sitter import Language

    return Language(tree_sitter_typescript.language_typescript())  # type: ignore[deprecated]


@pytest.fixture(scope="session")
def typescript_parser(typescript_language):
    """Tree-sitter Parser configured for TypeScript (session-scoped)."""
    from tree_sitter import Parser

    parser = Parser(typescript_language)
    return parser


@pytest.fixture
def parse_typescript(typescript_parser):
    """Parse TypeScript source code string → root node."""

    def _parse(code: str) -> "tree_sitter.Node":  # type: ignore[name-defined]
        tree = typescript_parser.parse(bytes(code, "utf-8"))
        return tree.root_node

    return _parse


@pytest.fixture(scope="session")
def java_language():
    """Tree-sitter Language for Java (session-scoped)."""
    import tree_sitter_java
    from tree_sitter import Language

    return Language(tree_sitter_java.language())  # type: ignore[deprecated]


@pytest.fixture(scope="session")
def java_parser(java_language):
    """Tree-sitter Parser configured for Java (session-scoped)."""
    from tree_sitter import Parser

    parser = Parser(java_language)
    return parser


@pytest.fixture
def parse_java(java_parser):
    """Parse Java source code string → root node."""

    def _parse(code: str) -> "tree_sitter.Node":  # type: ignore[name-defined]
        tree = java_parser.parse(bytes(code, "utf-8"))
        return tree.root_node

    return _parse
