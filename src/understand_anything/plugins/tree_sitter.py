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
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

from understand_anything.plugins.extractors.cpp import CppExtractor
from understand_anything.plugins.extractors.java import JavaExtractor
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


# Pre-load TypeScript/TSX grammars
TS_LANGUAGE = _load_grammar(tree_sitter_typescript, "language_typescript")
TSX_LANGUAGE = _load_grammar(tree_sitter_typescript, "language_tsx")

# Pre-load JavaScript grammar (separate package per plan)
JS_LANGUAGE = _load_grammar(tree_sitter_javascript, "language")

# Pre-load Python grammar
PY_LANGUAGE = _load_grammar(tree_sitter_python, "language")

# Pre-load C/C++ grammar
CPP_LANGUAGE = _load_grammar(tree_sitter_cpp, "language")

# Pre-load Java grammar
JAVA_LANGUAGE = _load_grammar(tree_sitter_java, "language")

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
    ExtractorRegistration(language_id="java", extractor=JavaExtractor()),
]

# ---------------------------------------------------------------------------
# Language → grammar mapping (extended as more languages are added)
# ---------------------------------------------------------------------------

_LANGUAGE_GRAMMARS: dict[str, Language] = {
    "typescript": TS_LANGUAGE,
    "tsx": TSX_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "python": PY_LANGUAGE,
    "cpp": CPP_LANGUAGE,
    "c": CPP_LANGUAGE,
    "java": JAVA_LANGUAGE,
}

#: 内置 TreeSitterPlugin 当前支持的所有语言 ID 列表。
#: 与 _BUILTIN_EXTRACTORS 保持一致，按注册顺序排列并去重。
SUPPORTED_TREE_SITTER_LANGUAGES: list[str] = list(
    dict.fromkeys(reg.language_id for reg in _BUILTIN_EXTRACTORS)
)

#: 内置文件扩展名 → 语言 ID 映射表，供 ``_detect_language`` 回退使用。
_BUILTIN_EXTENSION_MAP: dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".java": "java",
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

#: 内置完整文件名 → 语言 ID 映射表（如 Dockerfile、Makefile 等）。
_BUILTIN_FILENAME_MAP: dict[str, str] = {}


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
                每个 registration 可选携带 ``grammar``、``extensions``、
                ``filenames``；如果提供则自动注册到实例级映射。
        """
        self._extractors: dict[str, LanguageExtractor] = {}
        self._parsers: dict[str, Parser] = {}
        self._grammars: dict[str, Language] = {}
        self._extension_map: dict[str, str] = {}
        self._filename_map: dict[str, str] = {}

        # Register built-in extractors
        for reg in _BUILTIN_EXTRACTORS:
            self._extractors[reg.language_id] = reg.extractor
            if reg.grammar is not None:
                self._grammars[reg.language_id] = reg.grammar
            if reg.extensions is not None:
                for ext in reg.extensions:
                    self._extension_map[ext.lower()] = reg.language_id
            if reg.filenames is not None:
                for name in reg.filenames:
                    self._filename_map[name.lower()] = reg.language_id

        # Register user-supplied extractors
        if extra_extractors:
            for reg in extra_extractors:
                self._extractors[reg.language_id] = reg.extractor
                if reg.grammar is not None:
                    self._grammars[reg.language_id] = reg.grammar
                if reg.extensions is not None:
                    for ext in reg.extensions:
                        self._extension_map[ext.lower()] = reg.language_id
                if reg.filenames is not None:
                    for name in reg.filenames:
                        self._filename_map[name.lower()] = reg.language_id

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
        self,
        language_id: str,
        extractor: LanguageExtractor,
        grammar: Language | None = None,
        extensions: list[str] | None = None,
        filenames: list[str] | None = None,
    ) -> None:
        """Register an extractor (and optionally grammar + file mappings).

        Args:
            language_id: Language identifier to associate with the extractor.
            extractor: The ``LanguageExtractor`` instance to register.
            grammar: Optional ``tree_sitter.Language`` instance.  If
                provided, it is registered at instance level so that
                ``get_parser(language_id)`` can construct a parser.
            extensions: Optional file extensions to map to this language
                (e.g. ``[".go"]``).  Registered in the instance-level
                extension map so ``analyze_file`` can dispatch correctly.
            filenames: Optional exact filenames to map to this language
                (e.g. ``["Makefile"]``).  Case-insensitive.
        """
        self._extractors[language_id] = extractor
        if grammar is not None:
            self._grammars[language_id] = grammar
            self._parsers.pop(language_id, None)  # invalidate stale parser
        if extensions is not None:
            for ext in extensions:
                self._extension_map[ext.lower()] = language_id
        if filenames is not None:
            for name in filenames:
                self._filename_map[name.lower()] = language_id

    def register_grammar(self, language_id: str, grammar: Language) -> None:
        """Register a tree-sitter grammar for a language at instance level.

        实例级 grammar 优先级高于模块级 ``_LANGUAGE_GRAMMARS``，
        允许在运行时为已有或新的 language_id 注入 grammar。
        如果已有缓存的 ``Parser``，会被自动清除以确保新 grammar 生效。

        Args:
            language_id: 语言标识符。
            grammar: ``tree_sitter.Language`` 实例。
        """
        self._grammars[language_id] = grammar
        self._parsers.pop(language_id, None)  # invalidate stale parser

    def register_language(
        self,
        language_id: str,
        grammar: Language,
        extractor: LanguageExtractor,
        extensions: list[str] | None = None,
        filenames: list[str] | None = None,
    ) -> None:
        """同时注册 grammar、extractor 和文件映射 — 一步完成语言扩展。

        等效于依次调用 ``register_grammar(language_id, grammar)``、
        ``register_extractor(language_id, extractor)``，并注册文件映射。

        Args:
            language_id: 语言标识符。
            grammar: ``tree_sitter.Language`` 实例。
            extractor: ``LanguageExtractor`` 实例。
            extensions: 可选的文件扩展名列表（如 ``[".go"]``）。
                注册后 ``analyze_file("main.go", ...)`` 可正确分发到该语言。
            filenames: 可选的完整文件名列表（如 ``["Makefile"]``）。
                大小写不敏感。
        """
        self._grammars[language_id] = grammar
        self._parsers.pop(language_id, None)  # invalidate stale parser
        self._extractors[language_id] = extractor
        if extensions is not None:
            for ext in extensions:
                self._extension_map[ext.lower()] = language_id
        if filenames is not None:
            for name in filenames:
                self._filename_map[name.lower()] = language_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_grammar(self, language_id: str) -> Language:
        """Look up the tree-sitter grammar for a language ID.

        优先使用实例级 ``self._grammars``（通过 ``register_grammar`` 或
        ``ExtractorRegistration.grammar`` 注册），其次回退到模块级
        ``_LANGUAGE_GRAMMARS``。

        Args:
            language_id: A language identifier.

        Returns:
            The corresponding ``tree_sitter.Language``.

        Raises:
            ValueError: If the language is not supported.
        """
        grammar = self._grammars.get(language_id)
        if grammar is not None:
            return grammar
        grammar = _LANGUAGE_GRAMMARS.get(language_id)
        if grammar is None:
            msg = f"No tree-sitter grammar registered for '{language_id}'"
            raise ValueError(msg)
        return grammar

    def _detect_language(self, file_path: str) -> str:
        """Infer the language ID from file extension or filename.

        优先级（从高到低）：
        1. 实例级 ``self._extension_map``（通过 ``register_language`` 注入）
        2. 实例级 ``self._filename_map``
        3. 模块级 ``_BUILTIN_EXTENSION_MAP``（内置硬编码映射）
        4. 模块级 ``_BUILTIN_FILENAME_MAP``
        5. 返回 ``"unknown"``

        Args:
            file_path: Path or filename to inspect.

        Returns:
            A language ID string (e.g. ``"typescript"``, ``"javascript"``).
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        # Instance-level extension map (highest priority)
        if suffix in self._extension_map:
            return self._extension_map[suffix]

        # Instance-level filename map
        filename = path.name.lower()
        if filename in self._filename_map:
            return self._filename_map[filename]

        # Built-in extension map
        lang = _BUILTIN_EXTENSION_MAP.get(suffix)
        if lang is not None:
            return lang

        # Built-in filename map
        lang = _BUILTIN_FILENAME_MAP.get(filename)
        if lang is not None:
            return lang

        return "unknown"
