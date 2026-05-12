"""Non-code parsers — barrel export and registration.

Provides a ``register_all_parsers`` function that instantiates and registers
all 12 built-in parsers to a ``PluginRegistry``.  Each parser handles a
class of non-code files (Markdown, YAML, JSON, TOML, .env, Dockerfile, SQL,
GraphQL, Protobuf, Terraform, Makefile, Shell) and produces
``StructuralAnalysis`` with the relevant fields populated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.plugins.extractors.types import AnalyzerPlugin
    from understand_anything.plugins.registry import PluginRegistry

from understand_anything.plugins.parsers.dockerfile import DockerfileParser
from understand_anything.plugins.parsers.env import EnvParser
from understand_anything.plugins.parsers.graphql import GraphQLParser
from understand_anything.plugins.parsers.json_config import JSONConfigParser
from understand_anything.plugins.parsers.makefile import MakefileParser
from understand_anything.plugins.parsers.markdown import MarkdownParser
from understand_anything.plugins.parsers.protobuf import ProtobufParser
from understand_anything.plugins.parsers.shell import ShellParser
from understand_anything.plugins.parsers.sql import SQLParser
from understand_anything.plugins.parsers.terraform import TerraformParser
from understand_anything.plugins.parsers.toml_config import TOMLParser
from understand_anything.plugins.parsers.yaml_config import YAMLConfigParser


def _build_parsers() -> list[AnalyzerPlugin]:
    """Internal: instantiate all 12 parsers in deterministic order."""
    return [
        MarkdownParser(),
        YAMLConfigParser(),
        JSONConfigParser(),
        TOMLParser(),
        EnvParser(),
        DockerfileParser(),
        SQLParser(),
        GraphQLParser(),
        ProtobufParser(),
        TerraformParser(),
        MakefileParser(),
        ShellParser(),
    ]


def register_all_parsers(
    registry: PluginRegistry | None = None,
) -> list[AnalyzerPlugin]:
    """Create all 12 built-in non-code parsers and optionally register them.

    Each parser implements the ``AnalyzerPlugin`` interface.  When a
    ``PluginRegistry`` is provided, every parser is registered so that it
    becomes available for file-based dispatch (e.g.
    ``registry.get_plugin_for_file("README.md")`` returns the
    ``MarkdownParser``).

    Args:
        registry: Optional ``PluginRegistry`` instance.  When given, each
            parser is registered via ``registry.register(parser)``.

    Returns:
        A list of instantiated parser plugins in deterministic order.
        Callers who need direct access to individual parsers can use the
        returned list; callers who only need registry-based dispatch can
        ignore the return value.

    Example::

        from understand_anything.plugins.registry import PluginRegistry
        from understand_anything.plugins.parsers import register_all_parsers

        registry = PluginRegistry()
        register_all_parsers(registry)

        # Now dispatch works by file path
        analysis = registry.analyze_file("config.yaml", yaml_content)
    """
    parsers: list[AnalyzerPlugin] = _build_parsers()

    if registry is not None:
        for parser in parsers:
            registry.register(parser)

    return parsers


__all__ = [
    "DockerfileParser",
    "EnvParser",
    "GraphQLParser",
    "JSONConfigParser",
    "MakefileParser",
    "MarkdownParser",
    "ProtobufParser",
    "SQLParser",
    "ShellParser",
    "TOMLParser",
    "TerraformParser",
    "YAMLConfigParser",
    "register_all_parsers",
]
