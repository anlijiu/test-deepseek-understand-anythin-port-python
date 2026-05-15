"""Graph builder — incrementally constructs a KnowledgeGraph from file analyses.

Python port of the TypeScript ``GraphBuilder`` class (graph-builder.ts).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from understand_anything.types import (
    EdgeType,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    ProjectMeta,
)

if TYPE_CHECKING:
    from understand_anything.languages.registry import (
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

Complexity = Literal["simple", "moderate", "complex"]

# ---------------------------------------------------------------------------
# Kind → node type mapping (from KIND_TO_NODE_TYPE in graph-builder.ts)
# ---------------------------------------------------------------------------

KIND_TO_NODE_TYPE: dict[str, NodeType] = {
    "table": NodeType.TABLE,
    "view": NodeType.TABLE,
    "index": NodeType.TABLE,
    "message": NodeType.SCHEMA,
    "type": NodeType.SCHEMA,
    "enum": NodeType.SCHEMA,
    "resource": NodeType.RESOURCE,
    "module": NodeType.RESOURCE,
    "service": NodeType.SERVICE,
    "deployment": NodeType.SERVICE,
    "job": NodeType.PIPELINE,
    "stage": NodeType.PIPELINE,
    "target": NodeType.PIPELINE,
    "route": NodeType.ENDPOINT,
    "query": NodeType.ENDPOINT,
    "mutation": NodeType.ENDPOINT,
    "variable": NodeType.CONFIG,
    "output": NodeType.CONFIG,
}

# ---------------------------------------------------------------------------
# String → NodeType fallback mapping (for non-code file types)
# ---------------------------------------------------------------------------

_STR_TO_NODE_TYPE: dict[str, NodeType] = {
    "file": NodeType.FILE,
    "function": NodeType.FUNCTION,
    "class": NodeType.CLASS,
    "module": NodeType.MODULE,
    "concept": NodeType.CONCEPT,
    "config": NodeType.CONFIG,
    "document": NodeType.DOCUMENT,
    "service": NodeType.SERVICE,
    "table": NodeType.TABLE,
    "endpoint": NodeType.ENDPOINT,
    "pipeline": NodeType.PIPELINE,
    "schema": NodeType.SCHEMA,
    "resource": NodeType.RESOURCE,
    "domain": NodeType.DOMAIN,
    "flow": NodeType.FLOW,
    "step": NodeType.STEP,
    "article": NodeType.ARTICLE,
    "entity": NodeType.ENTITY,
    "topic": NodeType.TOPIC,
    "claim": NodeType.CLAIM,
    "source": NodeType.SOURCE,
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


# ---------------------------------------------------------------------------
# Node factory functions
# ---------------------------------------------------------------------------

def make_file_node(
    file_path: str,
    *,
    summary: str,
    tags: list[str],
    complexity: str,
) -> GraphNode:
    """Create a file-type ``GraphNode``.

    Args:
        file_path: Path to the source file.
        summary: Human-readable file summary.
        tags: Tags for categorization.
        complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
    """
    return GraphNode(
        id=f"file:{file_path}",
        type=NodeType.FILE,
        name=Path(file_path).name,
        filePath=file_path,
        summary=summary,
        tags=tags,
        complexity=cast("Complexity", complexity),
    )


def make_function_node(
    file_path: str,
    name: str,
    line_range: tuple[int, int],
    summary: str,
    complexity: str,
) -> GraphNode:
    """Create a function-type ``GraphNode``.

    Args:
        file_path: Path to the containing source file.
        name: Function name.
        line_range: Start/end line numbers (1-based, inclusive).
        summary: One-sentence function summary.
        complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
    """
    return GraphNode(
        id=f"function:{file_path}:{name}",
        type=NodeType.FUNCTION,
        name=name,
        filePath=file_path,
        lineRange=line_range,
        summary=summary,
        tags=[],
        complexity=cast("Complexity", complexity),
    )


def make_class_node(
    file_path: str,
    name: str,
    line_range: tuple[int, int],
    summary: str,
    complexity: str,
) -> GraphNode:
    """Create a class-type ``GraphNode``.

    Args:
        file_path: Path to the containing source file.
        name: Class name.
        line_range: Start/end line numbers (1-based, inclusive).
        summary: One-sentence class summary.
        complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
    """
    return GraphNode(
        id=f"class:{file_path}:{name}",
        type=NodeType.CLASS,
        name=name,
        filePath=file_path,
        lineRange=line_range,
        summary=summary,
        tags=[],
        complexity=cast("Complexity", complexity),
    )


def make_generic_node(
    node_id: str,
    node_type: NodeType,
    name: str,
    file_path: str,
    summary: str,
    complexity: str,
    *,
    tags: list[str] | None = None,
    line_range: tuple[int, int] | None = None,
) -> GraphNode:
    """Create a ``GraphNode`` with an arbitrary type.

    Args:
        node_id: Unique node identifier.
        node_type: The ``NodeType`` enum value.
        name: Display name.
        file_path: Path to the containing file.
        summary: Human-readable summary.
        complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
        tags: Optional tags list.
        line_range: Optional start/end line numbers.
    """
    return GraphNode(
        id=node_id,
        type=node_type,
        name=name,
        filePath=file_path,
        summary=summary,
        tags=tags or [],
        complexity=cast("Complexity", complexity),
        lineRange=line_range,
    )


# ---------------------------------------------------------------------------
# Edge factory functions
# ---------------------------------------------------------------------------

def make_contains_edge(source_id: str, target_id: str) -> GraphEdge:
    """Create a ``contains`` edge from parent to child."""
    return GraphEdge(
        source=source_id,
        target=target_id,
        type=EdgeType.CONTAINS,
        direction="forward",
        weight=1.0,
    )


def make_imports_edge(from_file_id: str, to_file_id: str) -> GraphEdge:
    """Create an ``imports`` edge between two files."""
    return GraphEdge(
        source=from_file_id,
        target=to_file_id,
        type=EdgeType.IMPORTS,
        direction="forward",
        weight=0.7,
    )


def make_calls_edge(
    caller_id: str, callee_id: str
) -> GraphEdge:
    """Create a ``calls`` edge between two functions."""
    return GraphEdge(
        source=caller_id,
        target=callee_id,
        type=EdgeType.CALLS,
        direction="forward",
        weight=0.8,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_node_type(type_str: str) -> NodeType:
    """Map a string to a ``NodeType`` enum value.

    Unknown strings fall back to ``NodeType.CONCEPT`` with a warning.
    """
    nt = _STR_TO_NODE_TYPE.get(type_str)
    if nt is None:
        logger.warning(
            '[GraphBuilder] Unknown node type string "%s"'
            ' — falling back to CONCEPT',
            type_str,
        )
        return NodeType.CONCEPT
    return nt


def _map_kind_to_node_type(kind: str) -> NodeType:
    """Map a definition kind to a canonical ``NodeType``.

    Unknown kinds fall back to ``NodeType.CONCEPT`` with a warning.
    """
    mapped = KIND_TO_NODE_TYPE.get(kind)
    if mapped is None:
        logger.warning(
            '[GraphBuilder] Unknown definition kind "%s"'
            ' — falling back to CONCEPT node type',
            kind,
        )
        return NodeType.CONCEPT
    return mapped


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------


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

        self._nodes: list[GraphNode] = []
        self._edges: list[GraphEdge] = []
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
    ) -> str:
        """Register a file node without structural analysis children.

        Args:
            file_path: Path to the source file.
            summary: Human-readable file summary.
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.

        Returns:
            The node ID assigned to this file.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        node = make_file_node(
            file_path, summary=summary, tags=tags, complexity=complexity
        )
        self._node_ids.add(node.id)
        self._nodes.append(node)
        return node.id

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
    ) -> str:
        """Register a file node with function/class children from analysis.

        Args:
            file_path: Path to the source file.
            analysis: Structural analysis result for the file.
            summary: Human-readable file summary (for the file node).
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.
            file_summary: Summary for the file node itself.
            summaries: Mapping from function/class name to 1-sentence summary.

        Returns:
            The file node ID assigned to this file.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        # Create the file node
        file_node = make_file_node(
            file_path,
            summary=file_summary,
            tags=tags,
            complexity=complexity,
        )
        file_id = file_node.id
        self._node_ids.add(file_id)
        self._nodes.append(file_node)

        # Create function nodes with "contains" edges
        for fn in analysis.functions:
            func_node = make_function_node(
                file_path,
                name=fn.name,
                line_range=fn.line_range,
                summary=summaries.get(fn.name, ""),
                complexity=complexity,
            )
            if func_node.id in self._node_ids:
                logger.warning(
                    '[GraphBuilder] Duplicate function node ID "%s" — skipping',
                    func_node.id,
                )
                continue
            self._node_ids.add(func_node.id)
            self._nodes.append(func_node)
            self._edges.append(make_contains_edge(file_id, func_node.id))

        # Create class nodes with "contains" edges, plus method child nodes
        for cls in analysis.classes:
            class_node = make_class_node(
                file_path,
                name=cls.name,
                line_range=cls.line_range,
                summary=summaries.get(cls.name, ""),
                complexity=complexity,
            )
            self._node_ids.add(class_node.id)
            self._nodes.append(class_node)
            self._edges.append(make_contains_edge(file_id, class_node.id))

            # Create method nodes as children of the class node.
            # Node ID format: function:{file}:{method}  (same as top-level
            # functions) so that call edges can reference methods by the
            # same scheme regardless of whether the caller/callee is a
            # top-level function or a method.
            for method_name in cls.methods:
                method_node = make_function_node(
                    file_path,
                    name=method_name,
                    line_range=cls.line_range,  # fallback: class range
                    summary=summaries.get(method_name, f"Method: {method_name}"),
                    complexity=complexity,
                )
                if method_node.id in self._node_ids:
                    logger.warning(
                        '[GraphBuilder] Duplicate method node ID "%s" — skipping',
                        method_node.id,
                    )
                    continue
                self._node_ids.add(method_node.id)
                self._nodes.append(method_node)
                self._edges.append(
                    make_contains_edge(class_node.id, method_node.id)
                )

        return file_id

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
            make_imports_edge(
                f"file:{from_file}", f"file:{to_file}"
            )
        )

    def add_import_edge_by_id(
        self, source_id: str, target_id: str
    ) -> None:
        """Add an ``imports`` edge using raw node IDs (deduplicated).

        Unlike ``add_import_edge`` which constructs IDs from file paths,
        this method accepts the actual node IDs, allowing correct edges
        for non-code files (``document:path``, ``config:path``, etc.).

        Args:
            source_id: Node ID of the importing file.
            target_id: Node ID of the imported file.
        """
        key = f"imports|{source_id}|{target_id}"
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self._edges.append(make_imports_edge(source_id, target_id))

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
            make_calls_edge(
                f"function:{caller_file}:{caller_func}",
                f"function:{callee_file}:{callee_func}",
            )
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
            node_type: The ``GraphNode.type`` to assign (string form, e.g.
                ``"document"``, ``"config"``).
            summary: Human-readable summary.
            tags: Tags for categorization.
            complexity: One of ``"simple"``, ``"moderate"``, ``"complex"``.

        Returns:
            The node ID assigned to this file.
        """
        lang = self._detect_language(file_path)
        if lang != "unknown":
            self._languages.add(lang)

        node_id = f"{node_type}:{file_path}"
        nt = _to_node_type(node_type)
        node = make_generic_node(
            node_id=node_id,
            node_type=nt,
            name=Path(file_path).name,
            file_path=file_path,
            summary=summary,
            complexity=complexity,
            tags=tags,
        )
        self._node_ids.add(node_id)
        self._nodes.append(node)
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
    ) -> str:
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

        Returns:
            The file node ID assigned to this non-code file.
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
                make_generic_node(
                    node_id=f"{defn.kind}:{file_path}:{defn.name}",
                    node_type=_map_kind_to_node_type(defn.kind),
                    name=defn.name,
                    file_path=file_path,
                    summary=(
                        f"{defn.kind}: {defn.name}"
                        f" ({len(defn.fields)} fields)"
                    ),
                    complexity=complexity,
                    line_range=defn.line_range,
                ),
                parent_id=file_id,
            )

        # Child nodes for services
        for svc in services or []:
            summary_parts = [f"Service {svc.name}"]
            if svc.image:
                summary_parts.append(f" (image: {svc.image})")
            self._add_child_node(
                make_generic_node(
                    node_id=f"service:{file_path}:{svc.name}",
                    node_type=NodeType.SERVICE,
                    name=svc.name,
                    file_path=file_path,
                    summary="".join(summary_parts),
                    complexity=complexity,
                ),
                parent_id=file_id,
            )

        # Child nodes for endpoints
        for ep in endpoints or []:
            name = f"{ep.method or ''} {ep.path}".strip()
            self._add_child_node(
                make_generic_node(
                    node_id=f"endpoint:{file_path}:{ep.path}",
                    node_type=NodeType.ENDPOINT,
                    name=name,
                    file_path=file_path,
                    summary=f"Endpoint: {name}",
                    complexity=complexity,
                    line_range=ep.line_range,
                ),
                parent_id=file_id,
            )

        # Child nodes for steps
        for step in steps or []:
            self._add_child_node(
                make_generic_node(
                    node_id=f"step:{file_path}:{step.name}",
                    node_type=NodeType.PIPELINE,
                    name=step.name,
                    file_path=file_path,
                    summary=f"Step: {step.name}",
                    complexity=complexity,
                    line_range=step.line_range,
                ),
                parent_id=file_id,
            )

        # Child nodes for resources
        for res in resources or []:
            self._add_child_node(
                make_generic_node(
                    node_id=f"resource:{file_path}:{res.name}",
                    node_type=NodeType.RESOURCE,
                    name=res.name,
                    file_path=file_path,
                    summary=f"Resource: {res.name} ({res.kind})",
                    complexity=complexity,
                    line_range=res.line_range,
                ),
                parent_id=file_id,
            )

        return file_id

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
            nodes=list(self._nodes),
            edges=list(self._edges),
            layers=[],
            tour=[],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_child_node(
        self, node: GraphNode, *, parent_id: str
    ) -> None:
        """Add a child node and a ``contains`` edge from *parent_id*.

        Skips duplicate node IDs with a warning.
        """
        if node.id in self._node_ids:
            logger.warning(
                '[GraphBuilder] Duplicate node ID "%s" — skipping', node.id
            )
            return
        self._node_ids.add(node.id)
        self._nodes.append(node)
        self._edges.append(make_contains_edge(parent_id, node.id))

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
