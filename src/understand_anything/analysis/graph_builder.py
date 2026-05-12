"""Graph builder — incrementally constructs a KnowledgeGraph from file analyses.

Python port of the TypeScript ``GraphBuilder`` class (graph-builder.ts).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from understand_anything.types import KnowledgeGraph, ProjectMeta

if TYPE_CHECKING:
    from understand_anything.languages.registry import (  # type: ignore[import-not-found]
        LanguageRegistry,
    )
    from understand_anything.types import (
        DefinitionInfo,
        EndpointInfo,
        ResourceInfo,
        ServiceInfo,
        StepInfo,
        StructuralAnalysis,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kind → node type mapping (from KIND_TO_NODE_TYPE in graph-builder.ts)
# ---------------------------------------------------------------------------

KIND_TO_NODE_TYPE: dict[str, str] = {
    "table": "table",
    "view": "table",
    "index": "table",
    "message": "schema",
    "type": "schema",
    "enum": "schema",
    "resource": "resource",
    "module": "resource",
    "service": "service",
    "deployment": "service",
    "job": "pipeline",
    "stage": "pipeline",
    "target": "pipeline",
    "route": "endpoint",
    "query": "endpoint",
    "mutation": "endpoint",
    "variable": "config",
    "output": "config",
}

# ---------------------------------------------------------------------------
# Default extension → language mapping (used when no LanguageRegistry provided)
# ---------------------------------------------------------------------------

_DEFAULT_EXTENSION_LANG: dict[str, str] = {
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
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".proto": "protobuf",
    ".sql": "sql",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".dockerfile": "dockerfile",
    ".env": "env",
    ".makefile": "makefile",
    ".sh": "shell",
    ".bash": "shell",
}


class GraphBuilder:
    """Incrementally builds a ``KnowledgeGraph`` from file analyses.

    Tracks nodes, edges, detected languages, and deduplication keys.
    Once all files have been added, call :meth:`build` to produce the
    final graph.

    Example::

        builder = GraphBuilder("my-project", "abc123")
        builder.add_file("src/app.ts", summary="Main app", tags=[], complexity="simple")
        graph = builder.build()
    """

    def __init__(
        self,
        project_name: str,
        git_hash: str,
        language_registry: LanguageRegistry | None = None,
    ) -> None:
        """Initialise the graph builder.

        Args:
            project_name: Human-readable project name.
            git_hash: Current Git commit SHA.
            language_registry: Optional ``LanguageRegistry`` for language
                detection.  When ``None``, a built-in extension mapping is
                used as a fallback.
        """
        self._project_name = project_name
        self._git_hash = git_hash
        self._language_registry = language_registry

        self._nodes: list[dict[str, Any]] = []
        self._edges: list[dict[str, Any]] = []
        self._languages: set[str] = set()
        self._node_ids: set[str] = set()
        self._edge_keys: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_file(
        self,
        file_path: str,
        *,
        summary: str,
        tags: list[str],
        complexity: str,
    ) -> None:
        """Register a file node without structural analysis children.

        Args:
            file_path: Path to the source file.
            summary: Human-readable file summary.
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        name = self._basename(file_path)
        node_id = f"file:{file_path}"

        self._node_ids.add(node_id)
        self._nodes.append(
            {
                "id": node_id,
                "type": "file",
                "name": name,
                "filePath": file_path,
                "summary": summary,
                "tags": tags,
                "complexity": complexity,
            }
        )

    def add_file_with_analysis(
        self,
        file_path: str,
        analysis: StructuralAnalysis,
        *,
        summary: str,
        tags: list[str],
        complexity: str,
        file_summary: str,
        summaries: dict[str, str],
    ) -> None:
        """Register a file node with function/class children from analysis.

        Args:
            file_path: Path to the source file.
            analysis: Structural analysis result for the file.
            summary: Human-readable file summary (for the file node).
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
            file_summary: Summary for the file node itself.
            summaries: Mapping from function/class name to 1-sentence summary.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        file_name = self._basename(file_path)
        file_id = f"file:{file_path}"

        # Create the file node
        self._node_ids.add(file_id)
        self._nodes.append(
            {
                "id": file_id,
                "type": "file",
                "name": file_name,
                "filePath": file_path,
                "summary": file_summary,
                "tags": tags,
                "complexity": complexity,
            }
        )

        # Create function nodes with "contains" edges
        for fn in analysis.functions:
            func_id = f"function:{file_path}:{fn.name}"
            self._node_ids.add(func_id)
            self._nodes.append(
                {
                    "id": func_id,
                    "type": "function",
                    "name": fn.name,
                    "filePath": file_path,
                    "lineRange": list(fn.line_range),
                    "summary": summaries.get(fn.name, ""),
                    "tags": [],
                    "complexity": complexity,
                }
            )
            self._edges.append(
                {
                    "source": file_id,
                    "target": func_id,
                    "type": "contains",
                    "direction": "forward",
                    "weight": 1,
                }
            )

        # Create class nodes with "contains" edges
        for cls in analysis.classes:
            class_id = f"class:{file_path}:{cls.name}"
            self._node_ids.add(class_id)
            self._nodes.append(
                {
                    "id": class_id,
                    "type": "class",
                    "name": cls.name,
                    "filePath": file_path,
                    "lineRange": list(cls.line_range),
                    "summary": summaries.get(cls.name, ""),
                    "tags": [],
                    "complexity": complexity,
                }
            )
            self._edges.append(
                {
                    "source": file_id,
                    "target": class_id,
                    "type": "contains",
                    "direction": "forward",
                    "weight": 1,
                }
            )

    def add_import_edge(self, from_file: str, to_file: str) -> None:
        """Add an ``imports`` edge between two files (deduplicated).

        Args:
            from_file: File path of the importing file.
            to_file: File path of the imported file.
        """
        key = f"imports|file:{from_file}|file:{to_file}"
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self._edges.append(
            {
                "source": f"file:{from_file}",
                "target": f"file:{to_file}",
                "type": "imports",
                "direction": "forward",
                "weight": 0.7,
            }
        )

    def add_call_edge(
        self,
        caller_file: str,
        caller_func: str,
        callee_file: str,
        callee_func: str,
    ) -> None:
        """Add a ``calls`` edge between two functions (deduplicated).

        Args:
            caller_file: File path containing the caller function.
            caller_func: Name of the caller function.
            callee_file: File path containing the callee function.
            callee_func: Name of the callee function.
        """
        key = (
            f"calls|function:{caller_file}:{caller_func}"
            f"|function:{callee_file}:{callee_func}"
        )
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self._edges.append(
            {
                "source": f"function:{caller_file}:{caller_func}",
                "target": f"function:{callee_file}:{callee_func}",
                "type": "calls",
                "direction": "forward",
                "weight": 0.8,
            }
        )

    def add_non_code_file(
        self,
        file_path: str,
        *,
        node_type: str,
        summary: str,
        tags: list[str],
        complexity: str,
    ) -> str:
        """Register a non-code file node and return its ID.

        Args:
            file_path: Path to the non-code file.
            node_type: The ``GraphNode.type`` to assign.
            summary: Human-readable summary.
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.

        Returns:
            The node ID assigned to this file.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        name = self._basename(file_path)
        node_id = f"{node_type}:{file_path}"

        self._node_ids.add(node_id)
        self._nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "name": name,
                "filePath": file_path,
                "summary": summary,
                "tags": tags,
                "complexity": complexity,
            }
        )
        return node_id

    def add_non_code_file_with_analysis(
        self,
        file_path: str,
        *,
        node_type: str,
        summary: str,
        tags: list[str],
        complexity: str,
        definitions: list[DefinitionInfo] | None = None,
        services: list[ServiceInfo] | None = None,
        endpoints: list[EndpointInfo] | None = None,
        steps: list[StepInfo] | None = None,
        resources: list[ResourceInfo] | None = None,
    ) -> None:
        """Register a non-code file with structured child nodes.

        Args:
            file_path: Path to the non-code file.
            node_type: The ``GraphNode.type`` for the file node.
            summary: Human-readable summary for the file node.
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
            definitions: Schema definitions (tables, messages, enums, etc.).
            services: Service/container definitions.
            endpoints: API endpoint definitions.
            steps: Pipeline/CI step definitions.
            resources: Infrastructure resource definitions.
        """
        file_id = self.add_non_code_file(
            file_path,
            node_type=node_type,
            summary=summary,
            tags=tags,
            complexity=complexity,
        )

        # Child nodes for definitions
        for defn in definitions or []:
            self._add_child_node(
                {
                    "id": f"{defn.kind}:{file_path}:{defn.name}",
                    "type": self._map_kind_to_node_type(defn.kind),
                    "name": defn.name,
                    "filePath": file_path,
                    "lineRange": list(defn.line_range),
                    "summary": (
                        f"{defn.kind}: {defn.name}"
                        f" ({len(defn.fields)} fields)"
                    ),
                    "tags": [],
                    "complexity": complexity,
                },
                parent_id=file_id,
            )

        # Child nodes for services
        for svc in services or []:
            summary_parts = [f"Service {svc.name}"]
            if svc.image:
                summary_parts.append(f" (image: {svc.image})")
            self._add_child_node(
                {
                    "id": f"service:{file_path}:{svc.name}",
                    "type": "service",
                    "name": svc.name,
                    "filePath": file_path,
                    "summary": "".join(summary_parts),
                    "tags": [],
                    "complexity": complexity,
                },
                parent_id=file_id,
            )

        # Child nodes for endpoints
        for ep in endpoints or []:
            name = f"{ep.method or ''} {ep.path}".strip()
            self._add_child_node(
                {
                    "id": f"endpoint:{file_path}:{ep.path}",
                    "type": "endpoint",
                    "name": name,
                    "filePath": file_path,
                    "lineRange": list(ep.line_range),
                    "summary": f"Endpoint: {name}",
                    "tags": [],
                    "complexity": complexity,
                },
                parent_id=file_id,
            )

        # Child nodes for steps
        for step in steps or []:
            self._add_child_node(
                {
                    "id": f"step:{file_path}:{step.name}",
                    "type": "pipeline",
                    "name": step.name,
                    "filePath": file_path,
                    "lineRange": list(step.line_range),
                    "summary": f"Step: {step.name}",
                    "tags": [],
                    "complexity": complexity,
                },
                parent_id=file_id,
            )

        # Child nodes for resources
        for res in resources or []:
            self._add_child_node(
                {
                    "id": f"resource:{file_path}:{res.name}",
                    "type": "resource",
                    "name": res.name,
                    "filePath": file_path,
                    "lineRange": list(res.line_range),
                    "summary": f"Resource: {res.name} ({res.kind})",
                    "tags": [],
                    "complexity": complexity,
                },
                parent_id=file_id,
            )

    def build(self) -> KnowledgeGraph:
        """Assemble and return the final ``KnowledgeGraph``.

        Returns:
            A fully populated ``KnowledgeGraph`` model ready for
            serialisation or validation.
        """
        return KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name=self._project_name,
                languages=sorted(self._languages),
                frameworks=[],
                description="",
                analyzedAt=datetime.now(timezone.utc).isoformat(),
                gitCommitHash=self._git_hash,
            ),
            nodes=list(self._nodes),  # type: ignore[arg-type]
            edges=list(self._edges),  # type: ignore[arg-type]
            layers=[],
            tour=[],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_child_node(
        self, node: dict[str, Any], *, parent_id: str
    ) -> None:
        """Add a child node and a ``contains`` edge from *parent_id*.

        Skips duplicate node IDs with a warning.
        """
        node_id = node["id"]
        if node_id in self._node_ids:
            logger.warning(
                '[GraphBuilder] Duplicate node ID "%s" — skipping', node_id
            )
            return
        self._node_ids.add(node_id)
        self._nodes.append(node)
        self._edges.append(
            {
                "source": parent_id,
                "target": node_id,
                "type": "contains",
                "direction": "forward",
                "weight": 1,
            }
        )

    def _map_kind_to_node_type(self, kind: str) -> str:
        """Map a definition kind to a canonical node type.

        Unknown kinds fall back to ``"concept"`` with a warning.
        """
        mapped = KIND_TO_NODE_TYPE.get(kind)
        if mapped is None:
            logger.warning(
                '[GraphBuilder] Unknown definition kind "%s"'
                ' — falling back to "concept" node type',
                kind,
            )
        return mapped or "concept"

    def _detect_language(self, file_path: str) -> str:
        """Infer the language ID from a file path.

        Tries the optional ``LanguageRegistry`` first, then falls back
        to the built-in extension mapping.
        """
        # Try LanguageRegistry if available
        if self._language_registry is not None:
            lang_config = self._language_registry.get_for_file(file_path)
            if lang_config is not None:
                return lang_config.id

        # Fall back to extension mapping
        suffix = Path(file_path).suffix.lower()
        # Handle special filenames (no extension or compound extensions)
        basename_lower = Path(file_path).name.lower()
        if basename_lower in ("dockerfile", "makefile"):
            return basename_lower
        if suffix == ".dockerfile":
            return "dockerfile"

        return _DEFAULT_EXTENSION_LANG.get(suffix, "unknown")

    @staticmethod
    def _basename(file_path: str) -> str:
        """Extract the filename from a path."""
        return Path(file_path).name
