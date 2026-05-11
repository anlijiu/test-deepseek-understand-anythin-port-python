"""Pydantic models and dataclasses — Python port of types.ts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeType(StrEnum):
    """21 node types: 5 code + 8 non-code + 3 domain + 5 knowledge."""

    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    CONCEPT = "concept"
    CONFIG = "config"
    DOCUMENT = "document"
    SERVICE = "service"
    TABLE = "table"
    ENDPOINT = "endpoint"
    PIPELINE = "pipeline"
    SCHEMA = "schema"
    RESOURCE = "resource"
    DOMAIN = "domain"
    FLOW = "flow"
    STEP = "step"
    ARTICLE = "article"
    ENTITY = "entity"
    TOPIC = "topic"
    CLAIM = "claim"
    SOURCE = "source"


class EdgeType(StrEnum):
    """35 edge types in 8 categories."""

    # Structural
    IMPORTS = "imports"
    EXPORTS = "exports"
    CONTAINS = "contains"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    # Behavioral
    CALLS = "calls"
    SUBSCRIBES = "subscribes"
    PUBLISHES = "publishes"
    MIDDLEWARE = "middleware"
    # Data flow
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    TRANSFORMS = "transforms"
    VALIDATES = "validates"
    # Dependencies
    DEPENDS_ON = "depends_on"
    TESTED_BY = "tested_by"
    CONFIGURES = "configures"
    # Semantic
    RELATED = "related"
    SIMILAR_TO = "similar_to"
    # Infrastructure
    DEPLOYS = "deploys"
    SERVES = "serves"
    PROVISIONS = "provisions"
    TRIGGERS = "triggers"
    # Schema / Data
    MIGRATES = "migrates"
    DOCUMENTS = "documents"
    ROUTES = "routes"
    DEFINES_SCHEMA = "defines_schema"
    # Domain
    CONTAINS_FLOW = "contains_flow"
    FLOW_STEP = "flow_step"
    CROSS_DOMAIN = "cross_domain"
    # Knowledge
    CITES = "cites"
    CONTRADICTS = "contradicts"
    BUILDS_ON = "builds_on"
    EXEMPLIFIES = "exemplifies"
    CATEGORIZED_UNDER = "categorized_under"
    AUTHORED_BY = "authored_by"


# ---------------------------------------------------------------------------
# Pydantic models — metadata objects
# ---------------------------------------------------------------------------


class KnowledgeMeta(BaseModel):
    """Optional knowledge metadata for article/entity/topic/claim/source nodes."""

    wikilinks: list[str] | None = None
    backlinks: list[str] | None = None
    category: str | None = None
    content: str | None = None


class DomainMeta(BaseModel):
    """Optional domain metadata for domain/flow/step nodes."""

    entities: list[str] | None = None
    business_rules: list[str] | None = Field(default=None, alias="businessRules")
    cross_domain_interactions: list[str] | None = Field(
        default=None, alias="crossDomainInteractions"
    )
    entry_point: str | None = Field(default=None, alias="entryPoint")
    entry_type: Literal["http", "cli", "event", "cron", "manual"] | None = (
        Field(default=None, alias="entryType")
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Pydantic models — graph entities
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """Graph node with 21 possible types."""

    id: str
    type: NodeType
    name: str
    file_path: str | None = Field(default=None, alias="filePath")
    line_range: tuple[int, int] | None = Field(default=None, alias="lineRange")
    summary: str
    tags: list[str] = Field(default_factory=list)
    complexity: Literal["simple", "moderate", "complex"]
    language_notes: str | None = Field(default=None, alias="languageNotes")
    domain_meta: DomainMeta | None = Field(default=None, alias="domainMeta")
    knowledge_meta: KnowledgeMeta | None = Field(
        default=None, alias="knowledgeMeta"
    )

    model_config = {"populate_by_name": True}


class GraphEdge(BaseModel):
    """Graph edge with rich relationship modeling."""

    source: str
    target: str
    type: EdgeType
    direction: Literal["forward", "backward", "bidirectional"]
    description: str | None = None
    weight: float = Field(ge=0.0, le=1.0)


class Layer(BaseModel):
    """Logical grouping of nodes into a layer."""

    id: str
    name: str
    description: str
    node_ids: list[str] = Field(alias="nodeIds")

    model_config = {"populate_by_name": True}


class TourStep(BaseModel):
    """A step in the learn-mode tour."""

    order: int
    title: str
    description: str
    node_ids: list[str] = Field(alias="nodeIds")
    language_lesson: str | None = Field(default=None, alias="languageLesson")

    model_config = {"populate_by_name": True}


class ProjectMeta(BaseModel):
    """Metadata about the analyzed project."""

    name: str
    languages: list[str]
    frameworks: list[str]
    description: str
    analyzed_at: str = Field(alias="analyzedAt")
    git_commit_hash: str = Field(alias="gitCommitHash")

    model_config = {"populate_by_name": True}


class KnowledgeGraph(BaseModel):
    """Root knowledge graph structure."""

    version: str
    kind: Literal["codebase", "knowledge"] | None = None
    project: ProjectMeta
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    layers: list[Layer]
    tour: list[TourStep]


# ---------------------------------------------------------------------------
# Pydantic models — configuration & persistence
# ---------------------------------------------------------------------------


class ThemeConfig(BaseModel):
    """Theme configuration for dashboard customization."""

    preset_id: str = Field(alias="presetId")
    accent_id: str = Field(alias="accentId")

    model_config = {"populate_by_name": True}


class AnalysisMeta(BaseModel):
    """Analysis metadata for persistence."""

    last_analyzed_at: str = Field(alias="lastAnalyzedAt")
    git_commit_hash: str = Field(alias="gitCommitHash")
    version: str
    analyzed_files: int = Field(alias="analyzedFiles")
    theme: ThemeConfig | None = None

    model_config = {"populate_by_name": True}


class ProjectConfig(BaseModel):
    """Project configuration for auto-update opt-in."""

    auto_update: bool = Field(alias="autoUpdate")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Dataclasses — structural analysis (lightweight, no validation needed)
# ---------------------------------------------------------------------------


@dataclass
class FunctionInfo:
    """Extracted function/method information."""

    name: str
    line_range: tuple[int, int]
    params: list[str] = field(default_factory=list)
    return_type: str | None = None


@dataclass
class ClassInfo:
    """Extracted class/struct/interface information."""

    name: str
    line_range: tuple[int, int]
    methods: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Extracted import statement."""

    source: str
    specifiers: list[str]
    line_number: int


@dataclass
class ExportInfo:
    """Extracted export statement."""

    name: str
    line_number: int
    is_default: bool = False


@dataclass
class SectionInfo:
    """Document section (heading)."""

    name: str
    level: int
    line_range: tuple[int, int]


@dataclass
class DefinitionInfo:
    """Parser-reported definition (table, message, enum, type, etc.)."""

    name: str
    kind: str
    line_range: tuple[int, int]
    fields: list[str] = field(default_factory=list)


@dataclass
class ServiceInfo:
    """Service/container definition."""

    name: str
    image: str | None = None
    ports: list[int] = field(default_factory=list)
    line_range: tuple[int, int] | None = None


@dataclass
class EndpointInfo:
    """HTTP/gRPC endpoint definition."""

    method: str | None = None
    path: str = ""
    line_range: tuple[int, int] = (0, 0)


@dataclass
class StepInfo:
    """Pipeline/CI step."""

    name: str
    line_range: tuple[int, int]


@dataclass
class ResourceInfo:
    """Infrastructure resource (Terraform, CloudFormation, etc.)."""

    name: str
    kind: str
    line_range: tuple[int, int]


@dataclass
class StructuralAnalysis:
    """Aggregate structural analysis result for a single file."""

    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    exports: list[ExportInfo] = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    definitions: list[DefinitionInfo] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    endpoints: list[EndpointInfo] = field(default_factory=list)
    steps: list[StepInfo] = field(default_factory=list)
    resources: list[ResourceInfo] = field(default_factory=list)


@dataclass
class CallGraphEntry:
    """Caller -> callee relationship."""

    caller: str
    callee: str
    line_number: int


@dataclass
class ImportResolution:
    """Resolved import path."""

    source: str
    resolved_path: str
    specifiers: list[str]


@dataclass
class ReferenceResolution:
    """Cross-file reference."""

    source: str
    target: str
    reference_type: str  # "file", "image", "schema", "service"
    line: int | None = None
