"""TreeSitterPlugin — unified tree-sitter file analysis.

Python port of the TypeScript TreeSitterPlugin.  The Python version is
significantly simpler because:

1. Native tree-sitter bindings are synchronous — no ``init()`` / WASM loading.
2. Language grammars are imported as normal Python packages.
3. No manual memory management (Python GC handles ``Parser`` / ``Tree``).

Approximate line-count reduction vs. Node: 300 → ~120 lines (~60 % less).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter_cpp
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

from understand_anything.plugins.extractors.cpp import CppExtractor
from understand_anything.plugins.extractors.python import PythonExtractor
from understand_anything.plugins.extractors.types import (
    AnalyzerPlugin,
    ExtractorRegistration,
)
from understand_anything.plugins.extractors.typescript import TypeScriptExtractor

if TYPE_CHECKING:
    from types import ModuleType

    from understand_anything.plugins.extractors.types import LanguageExtractor
    from understand_anything.types import (
        CallGraphEntry,
        StructuralAnalysis,
    )

from understand_anything.types import (
    ImportResolution,
    ReferenceResolution,
)

# ---------------------------------------------------------------------------
# Grammar lazy-loading cache
# ---------------------------------------------------------------------------

_GRAMMAR_CACHE: dict[str, Language] = {}


def _load_grammar(package: ModuleType, language_func_name: str) -> Language:
    """Load a tree-sitter ``Language`` from a Python grammar package.

    Many tree-sitter packages expose a ``language()`` top-level function;
    others (like tree-sitter-typescript) expose ``language_typescript()``
    and ``language_tsx()``.

    Args:
        package: The imported grammar package (e.g. ``tree_sitter_typescript``).
        language_func_name: Name of the language factory function on the package.

    Returns:
        A ``tree_sitter.Language`` instance.
    """
    key = f"{package.__name__}.{language_func_name}"
    if key not in _GRAMMAR_CACHE:
        factory = getattr(package, language_func_name)
        _GRAMMAR_CACHE[key] = Language(factory())  # type: ignore[deprecated]
    return _GRAMMAR_CACHE[key]


# Pre-load TypeScript/JavaScript grammars
TS_LANGUAGE = _load_grammar(tree_sitter_typescript, "language_typescript")
TSX_LANGUAGE = _load_grammar(tree_sitter_typescript, "language_tsx")

# Pre-load Python grammar
PY_LANGUAGE = _load_grammar(tree_sitter_python, "language")

# Pre-load C/C++ grammar
CPP_LANGUAGE = _load_grammar(tree_sitter_cpp, "language")

# ---------------------------------------------------------------------------
# Language → extractor mapping
# ---------------------------------------------------------------------------

_BUILTIN_EXTRACTORS: list[ExtractorRegistration] = [
    ExtractorRegistration(language_id="typescript", extractor=TypeScriptExtractor()),
    ExtractorRegistration(language_id="tsx", extractor=TypeScriptExtractor()),
    ExtractorRegistration(language_id="javascript", extractor=TypeScriptExtractor()),
    ExtractorRegistration(language_id="python", extractor=PythonExtractor()),
    ExtractorRegistration(language_id="cpp", extractor=CppExtractor()),
    ExtractorRegistration(language_id="c", extractor=CppExtractor()),
]

# ---------------------------------------------------------------------------
# Language → grammar mapping (extended as more languages are added)
# ---------------------------------------------------------------------------

_LANGUAGE_GRAMMARS: dict[str, Language] = {
    "typescript": TS_LANGUAGE,
    "tsx": TSX_LANGUAGE,
    "javascript": TS_LANGUAGE,
    "python": PY_LANGUAGE,
    "cpp": CPP_LANGUAGE,
    "c": CPP_LANGUAGE,
}


class TreeSitterPlugin(AnalyzerPlugin):
    """Plugin that uses tree-sitter grammars for structural file analysis.

    On construction, the plugin registers built-in extractors and optionally
    any user-supplied extractors for additional languages.

    Example::

        plugin = TreeSitterPlugin()
        analysis = plugin.analyze_file("src/app.ts", content)
        print(analysis.functions)
    """

    def __init__(
        self,
        extra_extractors: list[ExtractorRegistration] | None = None,
    ) -> None:
        """Initialise the plugin and register built-in + optional extractors.

        Args:
            extra_extractors: Additional language → extractor registrations
                provided by the caller (e.g. third-party plugins).
        """
        self._extractors: dict[str, LanguageExtractor] = {}
        self._parsers: dict[str, Parser] = {}

        # Register built-in extractors
        for reg in _BUILTIN_EXTRACTORS:
            self._extractors[reg.language_id] = reg.extractor

        # Register user-supplied extractors
        if extra_extractors:
            for reg in extra_extractors:
                self._extractors[reg.language_id] = reg.extractor

    # ------------------------------------------------------------------
    # AnalyzerPlugin interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "tree-sitter"

    @property
    def languages(self) -> list[str]:
        return list(self._extractors.keys())

    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis:
        """Analyze a single file using tree-sitter.

        The language is inferred from the file extension.

        Args:
            file_path: Path to the source file (used for language detection).
            content: The full source text of the file.

        Returns:
            A ``StructuralAnalysis`` populated by the matching extractor.

        Raises:
            ValueError: If no extractor is registered for the detected language.
        """
        language_id = self._detect_language(file_path)
        extractor = self._extractors.get(language_id)
        if extractor is None:
            msg = (
                f"No extractor registered for language '{language_id}'"
                f" (file: {file_path})"
            )
            raise ValueError(msg)

        parser = self.get_parser(language_id)
        tree = parser.parse(bytes(content, "utf-8"))
        return extractor.extract_structure(tree.root_node)

    def resolve_imports(
        self, file_path: str, content: str
    ) -> list[ImportResolution]:
        """Resolve relative imports to absolute file paths.

        Uses the file's directory as the resolution base.

        Args:
            file_path: Path to the source file.
            content: The full source text.

        Returns:
            List of resolved imports.
        """
        language_id = self._detect_language(file_path)
        extractor = self._extractors.get(language_id)
        if extractor is None:
            return []

        parser = self.get_parser(language_id)
        tree = parser.parse(bytes(content, "utf-8"))
        analysis = extractor.extract_structure(tree.root_node)
        base_dir = Path(file_path).parent

        resolved: list[ImportResolution] = []
        for imp in analysis.imports:
            resolved_path = str((base_dir / imp.source).resolve())
            resolved.append(
                ImportResolution(
                    source=imp.source,
                    resolved_path=resolved_path,
                    specifiers=imp.specifiers,
                )
            )
        return resolved

    def extract_call_graph(
        self, file_path: str, content: str
    ) -> list[CallGraphEntry]:
        """Extract call-graph entries from a single file.

        Args:
            file_path: Path to the source file.
            content: The full source text.

        Returns:
            List of ``CallGraphEntry`` objects.
        """
        language_id = self._detect_language(file_path)
        extractor = self._extractors.get(language_id)
        if extractor is None:
            return []

        parser = self.get_parser(language_id)
        tree = parser.parse(bytes(content, "utf-8"))
        return extractor.extract_call_graph(tree.root_node)

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution]:
        """Extract cross-file references (delegates to import resolution).

        Args:
            file_path: Path to the source file.
            content: The full source text.

        Returns:
            List of ``ReferenceResolution`` objects.
        """
        imports = self.resolve_imports(file_path, content)
        return [
            ReferenceResolution(
                source=file_path,
                target=imp.resolved_path,
                reference_type="file",
            )
            for imp in imports
        ]

    # ------------------------------------------------------------------
    # Parser management
    # ------------------------------------------------------------------

    def get_parser(self, language_id: str) -> Parser:
        """Return (or create and cache) a ``Parser`` for *language_id*.

        Args:
            language_id: A language identifier (e.g. ``"typescript"``).

        Returns:
            A ``tree_sitter.Parser`` configured for the language.

        Raises:
            ValueError: If no grammar is registered for *language_id*.
        """
        if language_id not in self._parsers:
            grammar = self._get_grammar(language_id)
            self._parsers[language_id] = Parser(grammar)
        return self._parsers[language_id]

    def register_extractor(
        self, language_id: str, extractor: LanguageExtractor
    ) -> None:
        """Register an extractor for a language at runtime.

        Args:
            language_id: Language identifier to associate with the extractor.
            extractor: The ``LanguageExtractor`` instance to register.
        """
        self._extractors[language_id] = extractor

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_grammar(language_id: str) -> Language:
        """Look up the tree-sitter grammar for a language ID.

        Args:
            language_id: A language identifier.

        Returns:
            The corresponding ``tree_sitter.Language``.

        Raises:
            ValueError: If the language is not supported.
        """
        grammar = _LANGUAGE_GRAMMARS.get(language_id)
        if grammar is None:
            msg = f"No tree-sitter grammar registered for '{language_id}'"
            raise ValueError(msg)
        return grammar

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Infer the language ID from a file extension.

        Args:
            file_path: Path or filename to inspect.

        Returns:
            A language ID string (e.g. ``"typescript"``, ``"javascript"``).
        """
        suffix = Path(file_path).suffix.lower()
        mapping: dict[str, str] = {
            ".ts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".mts": "typescript",
            ".cts": "typescript",
            ".py": "python",
            ".pyw": "python",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c++": "cpp",
            ".hpp": "cpp",
            ".hh": "cpp",
            ".hxx": "cpp",
            ".h++": "cpp",
        }
        return mapping.get(suffix, "unknown")
