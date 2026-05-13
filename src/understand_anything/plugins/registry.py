"""Plugin registry — maps languages to analyzer plugins.

Python port of the TypeScript ``PluginRegistry`` from
``@understand-anything/core``, with a built-in extension → language fallback
for use before the ``LanguageRegistry`` (Layer 7) is integrated.

When a ``LanguageRegistry`` is passed at construction, it takes priority
over the built-in extension mapping.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.plugins.extractors.types import AnalyzerPlugin
    from understand_anything.types import (
        CallGraphEntry,
        ImportResolution,
        ReferenceResolution,
        StructuralAnalysis,
    )

# ---------------------------------------------------------------------------
# Built-in extension → language mapping (fallback until Layer 7)
# ---------------------------------------------------------------------------

# fmt: off
_BUILTIN_EXTENSION_MAP: dict[str, str] = {
    # Code (handled by TreeSitterPlugin)
    ".ts":        "typescript",
    ".tsx":       "tsx",
    ".js":        "javascript",
    ".jsx":       "javascript",
    ".mjs":       "javascript",
    ".cjs":       "javascript",
    ".mts":       "typescript",
    ".cts":       "typescript",
    ".py":        "python",
    ".pyi":       "python",
    ".pyw":       "python",
    ".java":      "java",
    ".c":         "c",
    ".h":         "c",
    ".cpp":       "cpp",
    ".cc":        "cpp",
    ".cxx":       "cpp",
    ".c++":       "cpp",
    ".hpp":       "cpp",
    ".hh":        "cpp",
    ".hxx":       "cpp",
    ".h++":       "cpp",

    # Non-code (handled by dedicated parsers)
    ".md":        "markdown",
    ".mdx":       "markdown",
    ".yaml":      "yaml",
    ".yml":       "yaml",
    ".json":      "json",
    ".jsonc":     "jsonc",
    ".toml":      "toml",
    ".env":       "env",
    ".sql":       "sql",
    ".graphql":   "graphql",
    ".gql":       "graphql",
    ".proto":     "protobuf",
    ".tf":        "terraform",
    ".tfvars":    "terraform",
    ".mk":        "makefile",
    ".sh":        "shell",
    ".bash":      "shell",
    ".zsh":       "shell",

    # Filename-based (no extension, matched by basename)
    "Dockerfile":     "dockerfile",
    "Makefile":       "makefile",
    "Jenkinsfile":    "jenkinsfile",
    ".dockerignore":  "dockerfile",
}
# fmt: on


class PluginRegistry:
    """Maps language IDs to ``AnalyzerPlugin`` instances.

    Maintains an ordered list of registered plugins and a language → plugin
    lookup table.  File analysis is dispatched through
    :meth:`get_plugin_for_file`, which resolves the file's language via a
    ``LanguageRegistry`` (when available) or the built-in extension mapping.

    Example::

        registry = PluginRegistry()
        register_all_parsers(registry)
        registry.register(TreeSitterPlugin())

        analysis = registry.analyze_file("src/app.ts", content)
    """

    def __init__(
        self,
        language_registry: object | None = None,
    ) -> None:
        """Initialise the plugin registry.

        Args:
            language_registry: Optional ``LanguageRegistry`` instance for
                extension → language resolution.  When not provided, the
                built-in extension mapping is used as a fallback.
        """
        self._plugins: list[AnalyzerPlugin] = []
        self._language_map: dict[str, AnalyzerPlugin] = {}
        self._language_registry = language_registry

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: AnalyzerPlugin) -> None:
        """Register a plugin and map each of its languages to it.

        If a language is already registered, the last-registered plugin
        wins (deterministic priority for users who register parsers before
        TreeSitterPlugin, or vice versa).

        Args:
            plugin: An ``AnalyzerPlugin`` instance.
        """
        self._plugins.append(plugin)
        for lang in plugin.languages:
            self._language_map[lang] = plugin

    def unregister(self, name: str) -> None:
        """Remove a plugin by name and rebuild the language map.

        Args:
            name: The plugin's ``name`` attribute value.
        """
        self._plugins = [p for p in self._plugins if p.name != name]
        self._language_map.clear()
        for p in self._plugins:
            for lang in p.languages:
                self._language_map[lang] = p

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_plugin_for_language(self, language: str) -> AnalyzerPlugin | None:
        """Return the plugin registered for a given language ID.

        Args:
            language: Language identifier (e.g. ``"python"``, ``"yaml"``).

        Returns:
            The matching ``AnalyzerPlugin``, or ``None``.
        """
        return self._language_map.get(language)

    def get_plugin_for_file(self, file_path: str) -> AnalyzerPlugin | None:
        """Resolve the plugin responsible for a given file.

        Resolution order:
        1. If a ``LanguageRegistry`` was provided, delegate to it.
        2. Otherwise, use the built-in extension → language mapping.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            The ``AnalyzerPlugin`` that handles this file, or ``None``.
        """
        language_id = self._get_language_for_file(file_path)
        if language_id is None:
            return None
        return self.get_plugin_for_language(language_id)

    def _get_language_for_file(self, file_path: str) -> str | None:
        """Resolve the language ID for a file path.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            Language ID string, or ``None`` if the file type is unknown.
        """
        # Delegate to LanguageRegistry when available (Layer 7)
        if self._language_registry is not None:
            with contextlib.suppress(Exception):
                lr: object = self._language_registry
                lr_method = getattr(lr, "get_for_file", None) or getattr(
                    lr, "getForFile", None
                )
                if callable(lr_method):
                    lang_config = lr_method(file_path)
                    if lang_config is not None and hasattr(lang_config, "id"):
                        return str(lang_config.id)

        # Fallback: built-in extension mapping
        p = Path(file_path)
        if p.name in _BUILTIN_EXTENSION_MAP:
            return _BUILTIN_EXTENSION_MAP[p.name]

        return _BUILTIN_EXTENSION_MAP.get(p.suffix)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def analyze_file(
        self, file_path: str, content: str
    ) -> StructuralAnalysis | None:
        """Analyze a file through the appropriate plugin.

        Args:
            file_path: Path to the file.
            content: Full text content of the file.

        Returns:
            ``StructuralAnalysis`` from the matched plugin, or ``None``
            if no plugin handles the file type.
        """
        plugin = self.get_plugin_for_file(file_path)
        if plugin is None:
            return None
        return plugin.analyze_file(file_path, content)

    def resolve_imports(
        self, file_path: str, content: str
    ) -> list[ImportResolution] | None:
        """Resolve imports through the appropriate plugin.

        Args:
            file_path: Path to the file.
            content: Full text content of the file.

        Returns:
            List of ``ImportResolution``, or ``None`` if no plugin matches.
        """
        plugin = self.get_plugin_for_file(file_path)
        if plugin is None:
            return None
        return plugin.resolve_imports(file_path, content)

    def extract_call_graph(
        self, file_path: str, content: str
    ) -> list[CallGraphEntry] | None:
        """Extract call graph through the appropriate plugin.

        Args:
            file_path: Path to the file.
            content: Full text content of the file.

        Returns:
            List of ``CallGraphEntry``, or ``None`` if no plugin matches.
        """
        plugin = self.get_plugin_for_file(file_path)
        if plugin is None:
            return None
        return plugin.extract_call_graph(file_path, content)

    def extract_references(
        self, file_path: str, content: str
    ) -> list[ReferenceResolution] | None:
        """Extract cross-file references through the appropriate plugin.

        Args:
            file_path: Path to the file.
            content: Full text content of the file.

        Returns:
            List of ``ReferenceResolution``, or ``None`` if no plugin matches.
        """
        plugin = self.get_plugin_for_file(file_path)
        if plugin is None:
            return None
        return plugin.extract_references(file_path, content)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_plugins(self) -> list[AnalyzerPlugin]:
        """Return a copy of the registered plugin list in registration order.

        Returns:
            List of registered ``AnalyzerPlugin`` instances.
        """
        return list(self._plugins)

    def get_supported_languages(self) -> list[str]:
        """Return all language IDs with a registered plugin.

        Returns:
            Sorted list of supported language ID strings.
        """
        return sorted(self._language_map.keys())

    @property
    def plugin_count(self) -> int:
        """Number of registered plugins."""
        return len(self._plugins)

    @property
    def language_count(self) -> int:
        """Number of supported language IDs."""
        return len(self._language_map)
