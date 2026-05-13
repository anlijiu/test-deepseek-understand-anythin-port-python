"""Abstract base classes for language extractors and analyzer plugins.

Python port of TypeScript's ``LanguageExtractor`` and ``AnalyzerPlugin``
interfaces, adapted to Python's ABC pattern and native tree-sitter bindings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Language, Node

    from understand_anything.types import (
        CallGraphEntry,
        ImportResolution,
        ReferenceResolution,
        StructuralAnalysis,
    )


# ---------------------------------------------------------------------------
# LanguageExtractor — per-language AST extraction
# ---------------------------------------------------------------------------


class LanguageExtractor(ABC):
    """Language-specific structural extractor.

    Each concrete subclass handles one or more language IDs (e.g.
    ``["typescript", "javascript"]`` and extracts functions, classes,
    imports, exports, and call-graph entries from a tree-sitter AST.

    This is the Python equivalent of the TypeScript ``LanguageExtractor``
    interface defined in the original ``@understand-anything/core`` package.
    """

    @property
    @abstractmethod
    def language_ids(self) -> list[str]:
        """Language identifier(s) this extractor handles.

        Examples: ``["typescript"]``, ``["python"]``, ``["go"]``.
        """
        ...

    @abstractmethod
    def extract_structure(self, root_node: Node) -> StructuralAnalysis:
        """Extract functions, classes, imports, exports from the root AST node.

        Args:
            root_node: The root ``Node`` of a tree-sitter parse tree.

        Returns:
            A ``StructuralAnalysis`` containing all extracted structural
            information for the file.
        """
        ...

    @abstractmethod
    def extract_call_graph(self, root_node: Node) -> list[CallGraphEntry]:
        """Extract caller → callee relationships from the root AST node.

        Args:
            root_node: The root ``Node`` of a tree-sitter parse tree.

        Returns:
            A list of ``CallGraphEntry`` objects describing all call
            relationships found in the file.
        """
        ...


# ---------------------------------------------------------------------------
# AnalyzerPlugin — top-level file analysis plugin
# ---------------------------------------------------------------------------


class AnalyzerPlugin(ABC):
    """Top-level plugin interface for file analysis.

    An ``AnalyzerPlugin`` can handle one or more languages and provides
    higher-level file analysis beyond raw AST extraction.  Every
    ``AnalyzerPlugin`` **must** support ``analyze_file``; the remaining
    methods are optional hooks that return empty lists by default.

    This is the Python equivalent of the TypeScript ``AnalyzerPlugin``
    interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable plugin name (e.g. ``"tree-sitter"``)."""
        ...

    @property
    @abstractmethod
    def languages(self) -> list[str]:
        """Language IDs this plugin can analyze."""
        ...

    @abstractmethod
    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Analyze a single file and return its structural information.

        Args:
            file_path: Absolute or relative path to the source file.
            content: The full source text of the file.

        Returns:
            A ``StructuralAnalysis`` populated with extracted information.
        """
        ...

    def resolve_imports(
        self, file_path: str, content: str
    ) -> list[ImportResolution]:
        """Resolve import statements to absolute file paths (optional).

        Args:
            file_path: Path to the file containing the imports.
            content: The full source text of the file.

        Returns:
            List of resolved imports.  Default returns an empty list.
        """
        return []

    def extract_call_graph(
        self, file_path: str, content: str
    ) -> list[CallGraphEntry]:
        """Extract call-graph entries from a file (optional).

        Args:
            file_path: Path to the source file.
            content: The full source text of the file.

        Returns:
            List of ``CallGraphEntry`` objects.  Default returns an empty list.
        """
        return []

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution]:
        """Extract cross-file references from a file (optional).

        Args:
            file_path: Path to the source file.
            content: The full source text of the file.

        Returns:
            List of ``ReferenceResolution`` objects.  Default returns an
            empty list.
        """
        return []


# ---------------------------------------------------------------------------
# Extractor registration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExtractorRegistration:
    """Pairs a language ID with its concrete ``LanguageExtractor`` and optional grammar.

    Used by ``TreeSitterPlugin`` to build the internal language → extractor
    and language → grammar mappings during initialisation.

    Attributes:
        language_id: 语言标识符 (e.g. ``"typescript"``)。
        extractor: 对应的 ``LanguageExtractor`` 实例。
        grammar: 可选的 ``tree_sitter.Language`` 实例。
            提供后会在插件初始化时自动注册 grammar。
        extensions: 可选的文件扩展名列表 (e.g. ``[".go"]``)。
            提供后会自动注册到实例级扩展名映射，使 ``analyze_file`` 能识别。
        filenames: 可选的完整文件名列表 (e.g. ``["Makefile"]``)。
            提供后会自动注册到实例级文件名映射，大小写不敏感。
    """

    language_id: str
    extractor: LanguageExtractor
    grammar: Language | None = None
    extensions: list[str] | None = None
    filenames: list[str] | None = None


@dataclass
class PluginModuleInfo:
    """Metadata for a Python module that implements ``AnalyzerPlugin``.

    Used by ``PluginRegistry`` for discovery of third-party plugins.
    """

    module_path: str
    plugin_class: str
    config: dict[str, object] | None = field(default=None)
