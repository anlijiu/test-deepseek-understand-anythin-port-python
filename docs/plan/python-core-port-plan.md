# 技术方案：understand-anything-core 的 Python 移植

## 1. 概述

原 understand-anything-core 绝对位置 在 /home/an/workspace/ai/Understand-Anything/understand-anything-plugin/packages/core     , 它是项目 Understand-Anything ( 绝对位置  /home/an/workspace/ai/Understand-Anything/) 的核心模块

### 1.1 目标

将 `@understand-anything/core` (TypeScript, ~11,000 行) 完整移植为 Python 包 `understand-anything-core`，功能等价、API 风格 Python 化、测试覆盖等价。

### 1.2 核心结论

**完全可行。** 没有任何模块存在根本性的移植障碍。Python 版本在两个方面优于 Node 版本：

- **Tree-sitter 集成**：Python 的原生 `tree-sitter` 绑定是同步的，消除了 Node 版本中 300 行 WASM 加载、`createRequire`、异步 `init()` 等复杂性
- **部署简单性**：不再需要 WASM 运行时，不再有 Node 24 + darwin/arm64 的兼容问题

### 1.3 风险声明

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Tree-sitter 语法包版本在 PyPI 和 npm 间不同步 | 中 | 锁定语法包版本，用黄金数据跨平台验证 |
| 两个版本未来的功能一致性维护成本 | 中 | 共享测试夹具（JSON 格式），CI 两端都跑 |
| Python 打包生态碎片化 (pip/poetry/uv/pdm) | 低 | 选 uv 作为唯一工具链 |

---

## 2. 技术选型

### 2.1 运行时 & 打包

| 项目 | 选择 | 理由 |
|------|------|------|
| **Python 版本** | >= 3.11 | 3.11+ 有 `tomllib` 标准库、更好的 `Self` 类型 |
| **包管理器 / 构建** | uv + hatchling | uv 是目前最快的解析器；hatchling 是 PyPA 标准构建后端 |
| **类型检查** | mypy (strict mode) | 对标 TypeScript strict mode |
| **测试框架** | pytest + pytest-cov | 对标 vitest + v8 coverage |
| **Lint / Format** | ruff | 单一工具替代 flake8 + isort + black，极快 |

### 2.2 核心依赖映射

| npm 包 | Python 等价物 | 说明 |
|--------|---------------|------|
| `zod` | **pydantic >= 2.0** | 类型验证 + JSON Schema 导出，比 zod 更强大 |
| `web-tree-sitter` | **tree-sitter >= 0.24** | Python 原生绑定，同步 API |
| `tree-sitter-python` 等 | **tree-sitter-python** 等 | PyPI 上同名包，版本号可能不同 |
| `fuse.js` | **rapidfuzz** | 更快的模糊搜索实现 |
| `yaml` | **pyyaml** (CPython) 或 **ruamel.yaml** | pyyaml 用于基础解析 |
| `ignore` | **pathspec** | `.gitignore` 模式匹配 |
| `node:fs` / `node:path` | **pathlib.Path** | 标准库，比 Node.js 的 fs/path 更简洁 |
| `node:crypto` | **hashlib** | 标准库，SHA-256 |
| `node:child_process` | **subprocess** | 标准库 |

### 2.3 依赖关系图

```
understand-anything-core
├── pydantic >= 2.0          # Schema validation (替代 zod)
├── tree-sitter >= 0.24      # AST 解析核心
├── tree-sitter-python       # Python 语法 (完整列表见 §4.2)
├── tree-sitter-typescript
├── tree-sitter-javascript
├── tree-sitter-go
├── tree-sitter-rust
├── tree-sitter-java
├── tree-sitter-ruby
├── tree-sitter-php
├── tree-sitter-cpp
├── tree-sitter-c-sharp
├── rapidfuzz >= 3.0         # 模糊搜索
├── pathspec >= 0.12         # .gitignore 匹配
├── pyyaml >= 6.0            # YAML 解析
└── typing-extensions        # Python < 3.12 的类型增强
```

---

## 3. 包结构设计

```
understand-anything-core/
├── pyproject.toml
├── README.md
├── src/
│   └── understand_anything/
│       ├── __init__.py           # Public API re-exports (对标 src/index.ts)
│       ├── py.typed             # PEP 561 marker
│       │
│       ├── types.py             # All type definitions (对标 types.ts)
│       ├── schema.py            # Pydantic schemas + validation pipeline (对标 schema.ts)
│       │
│       ├── persistence/
│       │   ├── __init__.py      # Save/load graph, meta, fingerprints, config
│       │
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── graph_builder.py    # 图构建 (graph-builder.ts)
│       │   ├── llm_analyzer.py     # LLM prompt builders (llm-analyzer.ts)
│       │   ├── normalize.py        # 图标准化 (normalize-graph.ts)
│       │   ├── layer_detector.py   # 层次检测 (layer-detector.ts)
│       │   ├── tour_generator.py   # 导览生成 (tour-generator.ts)
│       │   ├── language_lesson.py  # 语言课程 (language-lesson.ts)
│       │   ├── fingerprint.py      # 文件指纹 (fingerprint.ts)
│       │   ├── staleness.py        # Git 变更检测 (staleness.ts)
│       │   └── change_classifier.py # 变更决策 (change-classifier.ts)
│       │
│       ├── search/
│       │   ├── __init__.py
│       │   ├── fuzzy.py           # Fuse.js 搜索 (search.ts)
│       │   └── semantic.py        # 向量搜索 (embedding-search.ts)
│       │
│       ├── ignore/
│       │   ├── __init__.py
│       │   ├── filter.py          # 忽略过滤器 (ignore-filter.ts)
│       │   └── generator.py       # .understandignore 生成器 (ignore-generator.ts)
│       │
│       ├── languages/
│       │   ├── __init__.py         # Barrel export
│       │   ├── types.py           # LanguageConfig + FrameworkConfig schemas
│       │   ├── registry.py        # LanguageRegistry
│       │   ├── framework_registry.py # FrameworkRegistry
│       │   └── configs/
│       │       ├── __init__.py     # Aggregates 40 language configs
│       │       ├── typescript.py
│       │       ├── python.py
│       │       ├── go.py
│       │       ├── ...            # 40 language config files
│       │       └── plaintext.py
│       │
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── registry.py        # PluginRegistry
│       │   ├── discovery.py       # Plugin config parsing
│       │   ├── tree_sitter.py     # TreeSitterPlugin (本来 300 行，Python 版 ~150 行)
│       │   ├── extractors/
│       │   │   ├── __init__.py     # Aggregates builtin extractors
│       │   │   ├── types.py       # LanguageExtractor abstract class
│       │   │   ├── base.py        # traverse(), find_child(), etc.
│       │   │   ├── typescript.py  # TS/JS 提取器
│       │   │   ├── python.py
│       │   │   ├── go.py
│       │   │   ├── rust.py
│       │   │   ├── java.py
│       │   │   ├── ruby.py
│       │   │   ├── php.py
│       │   │   ├── cpp.py
│       │   │   └── csharp.py
│       │   └── parsers/
│       │       ├── __init__.py     # Aggregates + register_all_parsers()
│       │       ├── markdown.py
│       │       ├── yaml_config.py
│       │       ├── json_config.py
│       │       ├── toml_config.py
│       │       ├── env.py
│       │       ├── dockerfile.py
│       │       ├── sql.py
│       │       ├── graphql.py
│       │       ├── protobuf.py
│       │       ├── terraform.py
│       │       ├── makefile.py
│       │       └── shell.py
│       │
│       └── frameworks/
│           ├── __init__.py
│           ├── django.py
│           ├── fastapi.py
│           ├── flask.py
│           ├── react.py
│           ├── nextjs.py
│           ├── express.py
│           ├── vue.py
│           ├── spring.py
│           ├── rails.py
│           └── gin.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # 共享 fixtures (黄金数据、示例图等)
│   ├── test_schema.py              # 模式验证测试
│   ├── test_types.py               # 类型定义测试
│   ├── test_persistence.py
│   ├── test_graph_builder.py
│   ├── test_normalize.py
│   ├── test_layer_detector.py
│   ├── test_tour_generator.py
│   ├── test_language_lesson.py
│   ├── test_fingerprint.py
│   ├── test_staleness.py
│   ├── test_change_classifier.py
│   ├── test_fuzzy_search.py
│   ├── test_semantic_search.py
│   ├── test_ignore.py
│   ├── test_plugins/
│   │   ├── test_tree_sitter.py
│   │   └── test_registry.py
│   ├── test_extractors/
│   │   ├── test_typescript.py
│   │   ├── test_python.py
│   │   ├── test_go.py
│   │   ├── ...                     # 每语言一个文件
│   │   └── test_csharp.py
│   ├── test_parsers/
│   │   ├── test_markdown.py
│   │   ├── test_yaml.py
│   │   ├── ...
│   │   └── test_shell.py
│   └── fixtures/                   # 测试夹具目录
│       ├── sample_graph.json
│       ├── sample_files/           # 各种语言的样本文件，用于提取器测试
│       │   ├── typescript/
│       │   ├── python/
│       │   └── ...
│       └── expected/               # 每个样本文件对应的预期输出 JSON
│           ├── typescript/
│           ├── python/
│           └── ...
│
└── scripts/
    ├── verify_parity.py            # 验证与 TS 版本的功能等价性
    └── generate_large_graph.py     # 对标 scripts/generate-large-graph.mjs
```

### 3.1 包导出对标

TypeScript 版本使用了 subpath exports 来隔离浏览器/Node 代码：

| TS Subpath | 内容 | Python 等价方案 |
|-----------|------|----------------|
| `.` (主入口) | 所有功能 | `from understand_anything import ...` |
| `./search` | 模糊搜索 (浏览器安全) | `from understand_anything.search import ...` |
| `./types` | 只有类型 (浏览器安全) | `from understand_anything.types import ...` |
| `./schema` | 只有模式 (浏览器安全) | `from understand_anything.schema import ...` |
| `./languages` | 语言注册表 | `from understand_anything.languages import ...` |

Python 中通过模块结构自然实现 —— 浏览器端只需不导入依赖 Node 的模块，无需显式的 subpath exports。

---

## 4. 类型系统设计

### 4.1 Pydantic v2 模型定义

```python
# types.py — Pydantic 模型（替代 TS interface）

from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import StrEnum

class NodeType(StrEnum):
    """21 node types"""
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
    """35 edge types in 8 categories"""
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
    # Infrastructure/Schema
    DEPLOYS = "deploys"
    SERVES = "serves"
    PROVISIONS = "provisions"
    TRIGGERS = "triggers"
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

class KnowledgeMeta(BaseModel):
    """Optional knowledge metadata"""
    wikilinks: Optional[list[str]] = None
    backlinks: Optional[list[str]] = None
    category: Optional[str] = None
    content: Optional[str] = None

class DomainMeta(BaseModel):
    """Optional domain metadata"""
    entities: Optional[list[str]] = None
    business_rules: Optional[list[str]] = Field(default=None, alias="businessRules")
    cross_domain_interactions: Optional[list[str]] = Field(default=None, alias="crossDomainInteractions")
    entry_point: Optional[str] = Field(default=None, alias="entryPoint")
    entry_type: Optional[Literal["http", "cli", "event", "cron", "manual"]] = Field(default=None, alias="entryType")

    model_config = {"populate_by_name": True}  # 同时支持 snake_case 和 camelCase

class GraphNode(BaseModel):
    id: str
    type: NodeType
    name: str
    file_path: Optional[str] = Field(default=None, alias="filePath")
    line_range: Optional[tuple[int, int]] = Field(default=None, alias="lineRange")
    summary: str
    tags: list[str] = Field(default_factory=list)
    complexity: Literal["simple", "moderate", "complex"]
    language_notes: Optional[str] = Field(default=None, alias="languageNotes")
    domain_meta: Optional[DomainMeta] = Field(default=None, alias="domainMeta")
    knowledge_meta: Optional[KnowledgeMeta] = Field(default=None, alias="knowledgeMeta")

    model_config = {"populate_by_name": True}

class GraphEdge(BaseModel):
    source: str
    target: str
    type: EdgeType
    direction: Literal["forward", "backward", "bidirectional"]
    description: Optional[str] = None
    weight: float = Field(ge=0.0, le=1.0)  # 0-1

# ... Layer, TourStep, ProjectMeta, KnowledgeGraph 类似定义

class KnowledgeGraph(BaseModel):
    version: str
    kind: Optional[Literal["codebase", "knowledge"]] = None
    project: ProjectMeta
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    layers: list[Layer]
    tour: list[TourStep]
```

### 4.2 插件接口（ABC 对标 TS interface）

```python
# plugins/extractors/types.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from tree_sitter import Node as TreeSitterNode  # 原生 tree-sitter Node 类型

@dataclass
class FunctionInfo:
    name: str
    line_range: tuple[int, int]
    params: list[str] = field(default_factory=list)
    return_type: Optional[str] = None

@dataclass
class ClassInfo:
    name: str
    line_range: tuple[int, int]
    methods: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)

@dataclass
class ImportInfo:
    source: str
    specifiers: list[str]
    line_number: int

@dataclass
class ExportInfo:
    name: str
    line_number: int
    is_default: bool = False

@dataclass
class StructuralAnalysis:
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
    caller: str
    callee: str
    line_number: int

class LanguageExtractor(ABC):
    """Language-specific extractor (对标 TS LanguageExtractor interface)"""

    @property
    @abstractmethod
    def language_ids(self) -> list[str]:
        """Language IDs this extractor handles"""
        ...

    @abstractmethod
    def extract_structure(self, root_node: TreeSitterNode) -> StructuralAnalysis:
        """Extract functions, classes, imports, exports from the root AST node"""
        ...

    @abstractmethod
    def extract_call_graph(self, root_node: TreeSitterNode) -> list[CallGraphEntry]:
        """Extract caller->callee relationships from the root AST node"""
        ...


class AnalyzerPlugin(ABC):
    """Top-level plugin interface (对标 TS AnalyzerPlugin)"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def languages(self) -> list[str]: ...

    @abstractmethod
    def analyze_file(self, file_path: str, content: str) -> StructuralAnalysis: ...

    def resolve_imports(self, file_path: str, content: str) -> list[ImportResolution]:
        """Optional — override in subclass"""
        return []

    def extract_call_graph(self, file_path: str, content: str) -> list[CallGraphEntry]:
        """Optional — override in subclass"""
        return []

    def extract_references(self, file_path: str, content: str) -> list[ReferenceResolution]:
        """Optional — override in subclass"""
        return []
```

---

## 5. Tree-sitter 集成 — Python vs Node 的关键差异

### 5.1 核心差异

Node 版本的 Tree-sitter 流程（简化前）：

```
1. await import("web-tree-sitter")         # 动态导入 WASM 模块
2. await Parser.init()                     # 初始化 WASM 运行时
3. 使用 createRequire() 解析 .wasm 文件路径  # Node CJS 兼容层
4. await Language.load(wasmPath)           # 异步加载各语法 WASM
5. new Parser() → setLanguage() → parse()  # 同步解析
6. parser.delete() / tree.delete()         # 手动内存管理
```

Python 版本的 Tree-sitter 流程：

```python
# 1. 导入是同步的，且为原生绑定
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

# 2. Language 直接从 Python 模块加载（无 WASM 文件路径解析问题）
PY_LANGUAGE = Language(tspython.language())

# 3. Parser 使用简单
parser = Parser(PY_LANGUAGE)
tree = parser.parse(bytes(content, "utf-8"))

# 4. 无需手动 delete（Python GC 处理）
```

### 5.2 TreeSitterPlugin 简化对比

| 功能 | Node 版本行数 | Python 版本行数 | 说明 |
|------|-------------|----------------|------|
| 导入 & 类型定义 | ~20 | ~10 | 无需 `createRequire`、动态 `import()` |
| `init()` 异步加载 | ~75 | **0** | Python 语法加载是同步的，不需要 init |
| `getParser()` | ~20 | ~10 | 使用 `Parser(Language(grammar.language()))` |
| `analyzeFile()` | ~30 | ~15 | 核心逻辑相同 |
| `resolveImports()` | ~25 | ~10 | `pathlib.Path` 比 `path.resolve` 更简洁 |
| `extractCallGraph()` | ~20 | ~10 | 核心逻辑相同 |
| 构造函数 & 注册 | ~60 | ~40 | 无 WASM 回退逻辑 |
| 总体 | ~300 | **~100** | **减少 ~67%** |

### 5.3 语法包管理

Python 的 tree-sitter 语言包在 PyPI 上的分布：

| 语言 | npm 包 | PyPI 包 | 加载方式 |
|------|--------|---------|---------|
| TypeScript | `tree-sitter-typescript` | `tree-sitter-typescript` | `Language(ts.language())` |
| JavaScript | `tree-sitter-javascript` | `tree-sitter-javascript` | `Language(js.language())` |
| Python | `tree-sitter-python` | `tree-sitter-python` | `Language(py.language())` |
| Go | `tree-sitter-go` | `tree-sitter-go` | `Language(go.language())` |
| Rust | `tree-sitter-rust` | `tree-sitter-rust` | `Language(rust.language())` |
| Java | `tree-sitter-java` | `tree-sitter-java` | `Language(java.language())` |
| Ruby | `tree-sitter-ruby` | `tree-sitter-ruby` | `Language(ruby.language())` |
| PHP | `tree-sitter-php` | `tree-sitter-php` | `Language(php.language())` |
| C/C++ | `tree-sitter-cpp` | `tree-sitter-cpp` | `Language(cpp.language())` |
| C# | `tree-sitter-c-sharp` | `tree-sitter-c-sharp` | `Language(cs.language())` |

**注意**：PyPI 包名与 npm 包名相同，但版本号不同步。需要在 `pyproject.toml` 中锁定具体版本并验证 AST 输出。

### 5.4 AST 遍历辅助函数

Python 版本使用 Python 的 `Node` 原生 API，与 web-tree-sitter 有细微差异：

```python
# base.py — 对标 base-extractor.ts

from tree_sitter import Node

def traverse(node: Node, visitor: "Callable[[Node], None]") -> None:
    """深度优先遍历 AST"""
    visitor(node)
    for child in node.children:
        traverse(child, visitor)

def get_string_value(node: Node) -> str:
    """提取去引号的字符串值"""
    for child in node.children:
        if child.type == "string_fragment":
            return child.text.decode("utf-8")
    text = node.text.decode("utf-8")
    return text.strip("'\"`")

def find_child(node: Node, type_name: str) -> Node | None:
    """找第一个匹配类型的子节点"""
    for child in node.children:
        if child.type == type_name:
            return child
    return None

def find_children(node: Node, type_name: str) -> list[Node]:
    """找所有匹配类型的子节点"""
    return [child for child in node.children if child.type == type_name]

def has_child_of_type(node: Node, type_name: str) -> bool:
    """检查是否有特定类型的子节点"""
    return any(child.type == type_name for child in node.children)
```

**关键差异**：Python 的 `node.text` 返回 `bytes`，需要 `.decode("utf-8")`。`node.children` 是 Python 列表（不需要 `childCount`/`child(i)` 循环）。

---

## 6. 分层实现计划

### 第 1 层：类型 & 模式 (预计 3-4 天)

- [ ] `types.py` — Pydantic 模型 + 纯数据 dataclasses
- [ ] `schema.py` — 完整的验证管道（sanitize → auto-fix → validate → referential integrity）
- [ ] 单元测试覆盖所有 alias 解析场景、边界条件

**复杂度**：中等。Pydantic v2 的 API 与 Zod 不同，但概念完全对应。
**关键测试**：用相同的 JSON 输入，验证 Python 和 TS 版本产生相同的验证输出。

### 第 2 层：基础设施 (预计 2-3 天)

- [ ] `persistence/__init__.py` — 对标 persistence/index.ts（save/load graph, meta, fingerprints, config）
- [ ] `ignore/filter.py` — pathspec 替代 `ignore`
- [ ] `ignore/generator.py` — `.understandignore` 生成
- [ ] `search/fuzzy.py` — rapidfuzz 替代 fuse.js
- [ ] `search/semantic.py` — numpy 实现余弦相似度

**复杂度**：低。主要是 API 翻译工作。

### 第 3 层：Tree-sitter 核心 (预计 5-7 天)

- [ ] `plugins/extractors/base.py` — 遍历辅助函数
- [ ] `plugins/extractors/types.py` — LanguageExtractor ABC + dataclasses
- [ ] `plugins/tree_sitter.py` — TreeSitterPlugin（~100 行）
- [ ] **10 个语言提取器**。按难度分组：

| 优先级 | 提取器 | 行数 (TS) | 说明 |
|--------|--------|----------|------|
| P0 | TypeScript/JavaScript | 494 | 参考实现，最重要 |
| P0 | Python | 353 | 关键语言 |
| P1 | Go | 402 |  |
| P1 | Rust | 509 | 最复杂提取器之一（宏系统） |
| P1 | Java | 449 |  |
| P2 | Ruby | 420 |  |
| P2 | PHP | 461 |  |
| P2 | C/C++ | 501 | 复杂（预处理器） |
| P2 | C# | 663 | 最大提取器 |

- [ ] 每种语言的 golden-data 测试

**复杂度**：高。这是整个移植的核心工作。
**策略**：先完成 TypeScript 和 Python 提取器并建立测试模式，再批量推进其余提取器。

### 第 4 层：图构建 & 标准化 (预计 3-4 天)

- [ ] `analysis/graph_builder.py` — 图构建器
- [ ] `analysis/normalize.py` — 噪声 LLM 输出处理
- [ ] `analysis/llm_analyzer.py` — 提示词构建/解析

**复杂度**：中等。纯算法逻辑，主要是直接翻译。

### 第 5 层：高级分析 (预计 2-3 天)

- [ ] `analysis/layer_detector.py` — 启发式 + LLM 层次检测
- [ ] `analysis/tour_generator.py` — 卡恩算法 + LLM 导览生成
- [ ] `analysis/language_lesson.py` — 概念检测 + 课程提示词
- [ ] `analysis/fingerprint.py` — SHA-256 + 结构指纹
- [ ] `analysis/staleness.py` — Git diff 封装
- [ ] `analysis/change_classifier.py` — 更新决策矩阵

**复杂度**：低到中等。

### 第 6 层：非代码解析器 (预计 2-3 天)

- [ ] 12 个解析器（markdown, yaml, json, toml, env, dockerfile, sql, graphql, protobuf, terraform, makefile, shell）
- [ ] 所有解析器注册到 PluginRegistry

**复杂度**：低。主要是正则模式和库 API 封装。

### 第 7 层：配置 & 注册表 (预计 1-2 天)

- [ ] `languages/configs/` — 40 种语言配置
- [ ] `languages/registry.py` — 扩展/文件名映射
- [ ] `languages/framework_registry.py` — 10 种框架检测
- [ ] `frameworks/` — 框架特定配置
- [ ] `plugins/discovery.py` — 插件配置解析

**复杂度**：低。声明式数据结构。

### 第 8 层：集成 & 打磨 (预计 3-5 天)

- [ ] 端到端集成测试（完整图构建管道）
- [ ] 跨 TS 版本的 golden-data 对比验证脚本
- [ ] 性能基准测试
- [ ] CI/CD 配置
- [ ] 文档（API 参考 + 贡献指南）

---

## 7. 测试策略

### 7.1 Golden Data Testing（关键质量保证）

这是确保移植正确性的关键：**对相同的输入文件，TS 和 Python 版本输出完全相同的 StructuralAnalysis**。

```python
# tests/conftest.py
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def ts_expected_output():
    """加载 TS 版本的预期输出作为 golden data"""
    with open(FIXTURES_DIR / "expected" / "typescript" / "sample.ts.json") as f:
        return json.load(f)

@pytest.fixture
def sample_ts_file():
    return (FIXTURES_DIR / "sample_files" / "typescript" / "sample.ts").read_text()
```

```python
# tests/extractors/test_typescript.py
def test_typescript_extractor_matches_node_output(sample_ts_file, ts_expected_output):
    """Python 提取器输出必须与 TS 版本一致"""
    extractor = TypeScriptExtractor()
    result = extractor.extract_structure(parse_ts(sample_ts_file))
    result_dict = dataclasses.asdict(result)
    assert result_dict == ts_expected_output
```

### 7.2 测试层级

| 层级 | 覆盖范围 | 工具 |
|------|--------|------|
| 单元测试 | 每个提取器、解析器、工具函数 | pytest |
| Schema 测试 | 所有验证路径（正常、自动修复、fatal） | pytest + pydantic |
| 集成测试 | 完整管道：文件 → 图 → 验证 | pytest |
| Golden data | 与 TS 版本交叉验证 | 自定义脚本 |
| 性能测试 | 大型图的解析速度对比 | pytest-benchmark |

### 7.3 持续集成

```yaml
# .github/workflows/test.yml (示例)
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --group dev
      - run: uv run pytest --cov=understand_anything
      - run: uv run mypy src/
      - run: uv run ruff check src/ tests/
```

---

## 8. 关键设计决策

### 8.1 数据类 vs Pydantic 模型

| 场景 | 选择 | 理由 |
|------|------|------|
| KnowledgeGraph 顶层结构 | Pydantic BaseModel | 需要 JSON Schema 导出、验证 |
| StructuralAnalysis 内部结构 | `@dataclass` | 轻量，不需要验证，性能更好 |
| 提取器/插件接口 | `ABC` + `@dataclass` | 抽象基类模式 |
| 语言/框架配置 | Pydantic BaseModel | 需要 Zod 级别的验证 |

### 8.2 camelCase 兼容

Pydantic v2 通过 `model_config = {"populate_by_name": True}` 同时支持 `camelCase` 和 `snake_case`：

```python
class GraphNode(BaseModel):
    file_path: Optional[str] = Field(default=None, alias="filePath")
    model_config = {"populate_by_name": True}

# 两种导入均可：
node = GraphNode(filePath="src/main.py")      # 从 JSON 加载（camelCase）
node = GraphNode(file_path="src/main.py")     # Python 风格（snake_case）
```

### 8.3 异步 vs 同步

Node 版本的 `TreeSitterPlugin.init()` 是异步的（WASM 加载）。Python 版本全部同步 —— native bindings 的 `Language()` 和 `Parser()` 都是同步的。这是一个简化点。

### 8.4 文件系统 API

```python
# Node: fs.readFileSync(path, "utf-8"), path.join(a, b)
# Python: Path(path).read_text(), Path(a) / b

from pathlib import Path

def save_graph(project_root: Path, graph: KnowledgeGraph) -> None:
    output_dir = project_root / ".understand-anything"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "knowledge-graph.json"
    output_file.write_text(graph.model_dump_json(indent=2))
```

---

## 9. 预算估算

| 阶段 | 内容 | 预估天数 |
|------|------|---------|
| 1 | 类型 & 模式 (Pydantic) | 3-4 天 |
| 2 | 基础设施 (持久化, 搜索, 忽略) | 2-3 天 |
| 3 | Tree-sitter 核心 + 10 提取器 | 5-7 天 |
| 4 | 图构建 & 标准化 | 3-4 天 |
| 5 | 高级分析 (层, 导览, 课程, 指纹) | 2-3 天 |
| 6 | 12 个非代码解析器 | 2-3 天 |
| 7 | 语言/框架配置 | 1-2 天 |
| 8 | 集成测试 & Golden data 验证 | 3-5 天 |
| 9 | 文档 & CI/CD | 1-2 天 |
| **总计** | | **22-33 天 (~4-6 周)** |

---

## 10. 后续扩展方向

移植完成后的潜在方向：

1. **FastAPI 服务包装** —— 将核心分析引擎暴露为 REST API，支持远程图构建
2. **NumPy/SciPy 加速** —— 在大图布局算法、图统计中使用矩阵运算
3. **更广泛的 tree-sitter 语法支持** —— Python 的语法包生态比 npm 更丰富
4. **PydanticAI 集成** —— 将 LLM 分析部分替换为 PydanticAI 的结构化输出
5. **PyPI 发布** —— `pip install understand-anything-core` 开箱即用
