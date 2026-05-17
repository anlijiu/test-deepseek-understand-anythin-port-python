
下面是一份我建议采用的新版 plan。核心原则是：**先审计证据，再扩展 schema；先定义查询语义，再做 SQLite；先做确定性跨文件解析，再引入模糊解析；每个阶段都必须有独立验收标准。**

这份 plan 可以替换 `docs/plan/update_plan_about_codegraph.md` 里原来的“补齐图构建短板”部分。原文件当前混入了 session log 和执行总结，建议后续单独拆成纯 plan 文件，例如 `docs/plan/codegraph_incremental_plan.md`。

**CodeGraph 能力补齐实施计划**

## 0. 背景与约束

本计划目标是逐步补齐本项目在代码图构建、引用解析、查询、存储和增量同步方面的能力。实施时必须遵守项目本地约束：

- 功能支持判断必须以本地文档或现有代码为准，未知即不支持。
- 每个阶段完成前必须通过：
  ```bash
  uv run ruff check src
  uv run ty check src
  uv run mypy src
  uv run pytest
  ```
- 核心领域对象尽早强类型化，外部边界可以使用 dict/json。
- CLI 胶水层放在 `src/understand_anything/cli`，使用 click，每个 top-level command 独立文件。
- 所有公开接口使用中文 Google 风格 docstring。

已知本地事实锚点：

- 当前状态文档描述 `types.py` 已包含 `GraphNode`、`GraphEdge`、`KnowledgeGraph`、`NodeType`、`EdgeType` 等核心模型，并提到 `NodeType` 有 21 种、`EdgeType` 有 35 种，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:22)。
- 当前状态文档描述 `GraphBuilder` 已支持 `add_file`、`add_file_with_analysis`、`add_import_edge`、`add_call_edge`、`add_non_code_file`、`add_non_code_file_with_analysis`、`build()`，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:26)。
- 当前状态文档描述已有 JSON 持久化，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:44)。
- 当前状态文档描述已有搜索模块 `search/fuzzy.py` 和 `search/semantic.py`，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:40)。
- 当前状态文档描述已有 fingerprint / change_classifier / staleness 增量相关模块，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:32)。
- 当前状态文档描述语言配置覆盖 40 种语言，但 tree-sitter extractor 当前列出 Python、TypeScript、Java、C++ 等主要实现，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:47) 和 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:56)。
- 当前状态文档描述已有 10 个框架配置和 `FrameworkRegistry`，见 [current_status_while_explore_phase_8_1.md](~/workspace/ai/test-deepseek-understand-anythin-port-python/docs/plan/current_status_while_explore_phase_8_1.md:52)。

## 1. 总体策略

不要一次性实现“节点扩展 + 跨文件解析 + SQLite + 查询 + watcher + CLI”。这会同时改变 schema、解析、存储、查询语义和用户接口，回归面过大。

采用分层推进：

1. **证据审计**：确认 schema 支持什么、extractor 实际产出什么、GraphBuilder 实际写入什么、Pipeline 实际持久化什么。
2. **领域模型扩展**：扩展节点和边，但保持旧结构兼容。
3. **确定性跨文件解析**：只做 import-based 高置信度解析，先不写入模糊边。
4. **图查询语义**：先在内存 graph 上定义 callers/callees/path/impact 等行为。
5. **SQLite 后端**：作为可选存储和查询后端，不替代 JSON 默认行为，直到等价测试稳定。
6. **框架感知解析**：只接入能产生明确 graph 价值的框架行为。
7. **增量同步与 watcher**：复用 fingerprint / staleness，而不是另起一套同步模型。
8. **CLI 暴露**：最后暴露稳定能力，避免早期 CLI 契约频繁变化。

## 2. 阶段 1：Baseline Audit

### 目标

建立一份可引用的事实表，避免基于印象判断“支持 / 不支持”。

### 输出文件

新增：

- `docs/plan/codegraph_baseline_audit.md`

### 审计维度

表格按以下列组织：

- 能力项
- schema 是否支持
- extractor 是否产出
- GraphBuilder 是否写入
- Pipeline 是否串联
- Persistence 是否保存
- Tests 是否覆盖
- 证据路径
- 当前结论

### 必须审计的能力

节点类型：

- file
- function
- class
- method
- variable
- enum
- interface
- type_alias
- module
- document
- config
- endpoint
- service
- resource

边类型：

- contains
- imports
- calls
- exports
- extends
- implements
- references
- type_of
- returns
- instantiates
- overrides
- decorates

解析能力：

- 同文件调用
- 跨文件 import 解析
- 跨文件 calls 解析
- class method 调用解析
- constructor 调用解析
- builtin / stdlib 过滤
- re-export / barrel 解析
- alias import 解析

存储与查询：

- JSON graph 保存和读取
- graph validation
- fuzzy search
- semantic search
- callers/callees
- path finding
- impact analysis
- SQLite / FTS5

### 验收标准

- `codegraph_baseline_audit.md` 中每个“支持”结论都必须有代码或文档路径。
- 没有证据的项目标记为“当前版本不支持”或“未确认，需后续验证”。
- 不修改 `src/` 代码。
- 运行：
  ```bash
  uv run ruff check src
  uv run ty check src
  uv run mypy src
  uv run pytest
  ```

## 3. 阶段 2：Graph Domain Model 扩展，但保持兼容

### 目标

扩展结构化分析结果，使 extractor 可以表达 method、variable、enum、interface、type alias、inheritance 等信息，同时避免破坏现有 `ClassInfo.methods` 用户。

### 设计原则

- 不直接把 `ClassInfo.methods: list[str]` 破坏性改成 `list[MethodInfo]`。
- 优先新增字段，例如：
  - `ClassInfo.method_details: list[MethodInfo]`
  - `StructuralAnalysis.variables`
  - `StructuralAnalysis.enums`
  - `StructuralAnalysis.interfaces`
  - `StructuralAnalysis.type_aliases`
  - `StructuralAnalysis.inheritance`
- 如果必须改变旧字段 shape，必须通过 validator 同时接受旧格式和新格式。
- 所有新增模型必须是强类型 dataclass 或 Pydantic model，不使用裸 dict 作为核心领域对象。

### 修改文件

- `src/understand_anything/types.py`
- `src/understand_anything/plugins/extractors/types.py`
- `src/understand_anything/plugins/extractors/base.py`
- `tests/test_language_types.py` 或新增 `tests/test_structural_types.py`

### 新增类型建议

```python
@dataclass
class MethodInfo:
    """类方法信息."""

    name: str
    signature: str
    parameters: list[str]
    return_type: str | None
    visibility: str | None
    is_static: bool
    is_async: bool
    line_start: int
    line_end: int


@dataclass
class VariableInfo:
    """变量信息."""

    name: str
    type_annotation: str | None
    value_preview: str | None
    scope: Literal["module", "class", "function"]
    line_number: int


@dataclass
class EnumInfo:
    """枚举信息."""

    name: str
    members: list[str]
    line_start: int
    line_end: int


@dataclass
class InterfaceInfo:
    """接口信息."""

    name: str
    methods: list[MethodInfo]
    properties: list[str]
    line_start: int
    line_end: int


@dataclass
class TypeAliasInfo:
    """类型别名信息."""

    name: str
    target: str
    line_number: int


@dataclass
class InheritanceInfo:
    """继承或实现关系."""

    source: str
    target: str
    relation: Literal["extends", "implements"]
    line_number: int
```

### 测试要求

新增测试覆盖：

- 新类型可构造。
- `StructuralAnalysis` 默认字段为空列表。
- 旧 `ClassInfo.methods = ["foo"]` 行为保持不破。
- 新 `ClassInfo.method_details = [MethodInfo(...)]` 可用。
- Pydantic / dataclass 序列化路径不破坏已有测试。

### 验收标准

- 现有测试不需要大规模改 fixture。
- `ClassInfo.methods` 的旧 shape 仍可工作。
- 所有质量门禁通过。

## 4. 阶段 3：Extractor 产出扩展

### 目标

在 Python、TypeScript、Java、C++ extractor 中逐步产出阶段 2 新增的结构化信息。

### 实施顺序

1. Python
2. TypeScript
3. Java
4. C++

每种语言单独 PR / 单独提交，避免一次性修改四个 extractor 导致定位困难。

### Python 支持范围

- module-level variable
- class method details
- Enum class
- Protocol class
- type alias
- inheritance extends

### TypeScript 支持范围

- interface
- enum
- type alias
- variable declaration
- class method details
- extends / implements

### Java 支持范围

- interface
- enum
- class method details
- extends / implements

### C++ 支持范围

- struct
- enum
- class method details
- inheritance

### 修改文件

- `src/understand_anything/plugins/extractors/python.py`
- `src/understand_anything/plugins/extractors/typescript.py`
- `src/understand_anything/plugins/extractors/java.py`
- `src/understand_anything/plugins/extractors/cpp.py`
- `tests/test_extractors/test_python.py`
- `tests/test_extractors/test_typescript.py`
- `tests/test_extractors/test_java.py`
- `tests/test_extractors/test_cpp.py`

### 验收标准

每种语言必须新增 fixture 级测试：

- 输入源码片段。
- 调用 extractor。
- 断言新增结构化字段。
- 断言原有 functions/classes/imports/exports 不回归。
- 每种语言完成后单独跑：
  ```bash
  uv run pytest tests/test_extractors/test_<language>.py
  uv run ruff check src
  uv run ty check src
  uv run mypy src
  ```

## 5. 阶段 4：GraphBuilder 写入扩展节点和边

### 目标

让 `GraphBuilder` 把阶段 3 产出的结构化信息转换成 graph node / edge。

### 设计原则

- 先只写确定性节点和边。
- 不把低置信度推断写入主图。
- 所有 node id 和 edge id 必须稳定。
- 所有工厂函数使用正常 Pydantic 构造，不使用 `model_construct()` 绕过校验。
- 新边必须通过 schema validation。

### 新增节点

- method
- variable
- enum
- interface
- type_alias

### 新增边

- file contains method / variable / enum / interface / type_alias
- class contains method
- class extends class
- class implements interface
- file exports symbol
- variable type_of type_alias 或 interface，如果能确定

### 修改文件

- `src/understand_anything/analysis/graph_builder.py`
- `src/understand_anything/schema.py`，仅当 schema alias 或 validation 需要扩展
- `tests/test_graph_builder.py`

### 验收测试

新增测试：

- `add_file_with_analysis()` 可以写入 method nodes。
- class method 使用稳定 id，例如 `method:src/a.py:ClassName.method_name`。
- interface / enum / type_alias 生成对应 nodes。
- extends / implements edges 不产生悬挂边。
- graph validation 通过。
- invalid complexity 等非法输入仍被拒绝。

### 验收标准

- `GraphBuilder` 输出的新 graph 能被 `validate_graph()` 接受。
- 旧 graph builder 测试全部通过。
- 所有质量门禁通过。

## 6. 阶段 5：确定性跨文件引用解析

### 目标

实现高置信度、可解释的跨文件调用和引用解析。第一版只做 import-based 确定性解析，不做 fuzzy 写图。

### 非目标

第一版不支持：

- 任意 fuzzy 边写入主图。
- 动态 import 的完整语义。
- 运行时 monkey patch。
- 未导入同名符号的猜测解析。
- 跨语言引用解析。

### 新增文件

- `src/understand_anything/analysis/resolution/__init__.py`
- `src/understand_anything/analysis/resolution/types.py`
- `src/understand_anything/analysis/resolution/import_resolver.py`
- `src/understand_anything/analysis/resolution/builtins.py`

`name_matcher.py` 可以推迟到 fuzzy 阶段，不在第一版实现。

### 核心类型

```python
@dataclass
class UnresolvedRef:
    """尚未解析的引用."""

    source_file: str
    source_symbol: str
    target_name: str
    ref_kind: Literal["call", "type", "inheritance", "instantiation"]
    line_number: int


@dataclass
class ResolvedRef:
    """已解析的引用."""

    source_file: str
    source_symbol: str
    target_file: str
    target_symbol: str
    ref_kind: Literal["call", "type", "inheritance", "instantiation"]
    confidence: float
    strategy: Literal["import_exact", "same_file", "builtin_filtered"]
    line_number: int
```

### Pipeline 集成

- 现有 pipeline 先完成所有文件节点注册。
- 建立 `symbol_index`：
  - exported symbol -> file
  - top-level function -> file
  - class -> file
  - method -> class/file
- 解析 imports。
- 只为 `confidence >= 0.9` 的引用写入主图。
- 未解析引用输出 diagnostics，不写入 graph。

### 修改文件

- `src/understand_anything/pipeline.py`
- `src/understand_anything/plugins/extractors/types.py`
- `src/understand_anything/plugins/extractors/base.py`
- 各语言 extractor，按需新增 unresolved refs 产出

### 测试 fixture

新增目录：

- `tests/fixtures/resolution/python_simple/`
- `tests/fixtures/resolution/python_alias_import/`
- `tests/fixtures/resolution/typescript_simple/`
- `tests/fixtures/resolution/typescript_reexport/`

### 验收测试

- `from service import do_work; do_work()` 解析到 `service.py:do_work`。
- `import service as svc; svc.do_work()` 解析到 `service.py:do_work`。
- builtin 调用如 `print()`、`len()` 不写 calls edge。
- 两个文件都有同名函数但只有一个被 import 时，解析到 import 目标。
- 无法确定的同名调用不写入主图。
- 所有新增边无 dangling endpoint。

## 7. 阶段 6：内存图查询语义

### 目标

先在 `KnowledgeGraph` 内存对象上定义稳定查询语义，为后续 SQLite 等价实现打基础。

### 新增文件

- `src/understand_anything/analysis/graph_traversal.py`
- `src/understand_anything/analysis/graph_queries.py`

### 能力范围

`GraphTraverser`：

- `bfs(start_node_id, max_depth=None, edge_types=None)`
- `dfs(start_node_id, max_depth=None, edge_types=None)`
- `shortest_path(source_id, target_id, edge_types=None)`
- `impact_radius(start_node_id, depth=2)`
- `callers(symbol_id)`
- `callees(symbol_id)`
- `type_hierarchy(type_id)`

`GraphQueryManager`：

- `find_node(node_id)`
- `find_nodes_by_name(name)`
- `find_nodes_by_type(node_type)`
- `find_callers(symbol_name_or_id)`
- `find_callees(symbol_name_or_id)`
- `find_importers(file_path)`
- `find_dependencies(file_path)`
- `find_dependents(file_path)`

### 设计原则

- 查询结果返回强类型对象，不返回裸 dict。
- 默认只遍历确定性边。
- 对 fuzzy / low-confidence 边预留过滤字段，但此阶段不实现 fuzzy。
- 如果 graph 中存在 dangling edge，查询层应跳过并记录 warning，不应崩溃。

### 测试要求

新增：

- `tests/test_graph_traversal.py`
- `tests/test_graph_queries.py`

测试覆盖：

- BFS / DFS 顺序稳定。
- shortest path 找到最短路径。
- callers / callees 只看 calls / instantiates 等语义边。
- impact radius 可限制深度。
- 循环图不会无限递归。
- 空图返回空结果。

## 8. 阶段 7：SQLite 后端作为可选后端

### 目标

新增 SQLite 存储和查询后端，但不立即替代 JSON 默认后端。

### 非目标

- 不删除 JSON 持久化。
- 不改变默认输出格式。
- 不要求所有 CLI 默认使用 SQLite。
- 不引入 ORM。

### 新增文件

- `src/understand_anything/persistence/sqlite_backend.py`
- `src/understand_anything/persistence/migrations.py`
- `src/understand_anything/persistence/sqlite_queries.py`

### 数据库路径

默认：

```text
<project_root>/.understand-anything/knowledge-graph.sqlite
```

### 表结构 v1

建议最小 schema：

```sql
CREATE TABLE graph_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    summary TEXT,
    language TEXT,
    complexity TEXT,
    data_json TEXT NOT NULL
);

CREATE TABLE edges (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    type TEXT NOT NULL,
    confidence REAL,
    data_json TEXT NOT NULL
);

CREATE INDEX idx_nodes_type ON nodes(type);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_nodes_file_path ON nodes(file_path);
CREATE INDEX idx_edges_source ON edges(source);
CREATE INDEX idx_edges_target ON edges(target);
CREATE INDEX idx_edges_type ON edges(type);
```

FTS5：

```sql
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    id UNINDEXED,
    name,
    summary,
    file_path
);
```

如果 FTS5 不可用，fallback 到 `LIKE`。

### API 设计

```python
class SqliteGraphBackend:
    """SQLite 图存储后端."""

    def save_graph(self, graph: KnowledgeGraph) -> None: ...
    def load_graph(self) -> KnowledgeGraph | None: ...
    def query_nodes(self, query: GraphQuery) -> list[GraphNode]: ...
    def query_edges(self, query: GraphQuery) -> list[GraphEdge]: ...
```

不要把 JSON 和 SQLite 强行塞进一个过宽的 `DatabaseBackend`，先保持两个后端清晰独立，再在 pipeline 层做选择。

### Pipeline 参数

```python
backend: Literal["json", "sqlite"] = "json"
```

### 等价测试

新增：

- `tests/test_persistence_sqlite.py`
- `tests/test_sqlite_graph_queries.py`

测试覆盖：

- save/load graph roundtrip。
- JSON backend 和 SQLite backend 对同一 graph 返回同样 nodes/edges。
- FTS 搜索可用时走 FTS。
- FTS 不可用时 fallback 到 LIKE。
- migration `PRAGMA user_version` 正常推进。
- 写入事务失败时不留下半截 graph。

## 9. 阶段 8：框架感知解析

### 目标

把框架检测结果转化为明确的 graph 增益，而不是只把 framework 名称挂到 metadata。

### 分阶段支持

第一批只做最明确、最容易验收的框架：

- FastAPI
- Django
- React
- Spring

### FastAPI 支持

识别：

```python
@app.get("/users/{id}")
def get_user(id: str): ...
```

产出：

- endpoint node: `endpoint:src/api.py:GET /users/{id}`
- contains edge: file -> endpoint
- handles edge 或 references edge: endpoint -> function

### Django 支持

识别：

- `urls.py` 中 path / re_path
- view function / class

产出：

- endpoint node
- route -> view reference

### React 支持

识别：

- component function / class
- JSX component usage

产出：

- component node，如果已有 node type 支持
- renders / references edge，若 schema 支持；否则先用 references

### Spring 支持

识别：

- `@RestController`
- `@GetMapping`
- `@PostMapping`

产出：

- endpoint node
- endpoint -> method edge

### 修改文件

- `src/understand_anything/frameworks/`
- `src/understand_anything/analysis/resolution/`
- `src/understand_anything/pipeline.py`
- `tests/test_framework_registry.py`
- 新增 `tests/test_framework_resolution.py`

### 验收标准

- 每个框架至少一个 fixture。
- 框架未检测到时不影响普通图构建。
- 框架误检有测试，例如 `preact` 不误判为 `react` 这类已有防误报思路继续保持。
- 框架解析产出的 node/edge 通过 graph validation。

## 10. 阶段 9：增量同步与文件监听

### 目标

基于现有 fingerprint / staleness 能力实现增量同步，再用 watcher 触发它。

### 非目标

- 第一版不要求复杂 rename detection。
- 第一版不要求跨进程 daemon。
- 第一版不要求实时 UI。

### 新增文件

- `src/understand_anything/sync/__init__.py`
- `src/understand_anything/sync/index.py`
- `src/understand_anything/sync/watcher.py`

### 复用现有模块

必须优先复用：

- `analysis/fingerprint.py`
- `analysis/change_classifier.py`
- `analysis/staleness.py`

### 同步行为

`IncrementalSyncer`：

- 输入 changed files。
- 读取旧 graph 和 fingerprints。
- 对每个文件计算 change level。
- 对结构变化文件重新分析。
- 删除文件时移除对应 nodes 和相关 edges。
- 新文件时新增 nodes 和相关 edges。
- 合并后重新 validate graph。
- 成功后原子写入 graph 和 fingerprints。

### Watcher 行为

`FileWatcher`：

- 使用 watchdog 可选依赖。
- 2s debounce。
- 忽略 `.understand-anything`、`.git`、`__pycache__`、`.venv`、`node_modules`。
- 只把事件转交给 `IncrementalSyncer`。
- watcher 不直接改 graph。

### pyproject

`watchdog` 保持可选依赖：

```toml
[project.optional-dependencies]
watch = ["watchdog"]
```

如果已有 optional group，则只增补，不重复创建。

### 测试

新增：

- `tests/test_sync_index.py`
- `tests/test_sync_watcher.py`

测试覆盖：

- 新增文件。
- 修改函数签名。
- 修改函数体调用。
- 删除文件清理 dangling edges。
- 多事件 debounce 后只触发一次 sync。
- 未安装 watchdog 时给出明确错误，不影响核心包导入。

## 11. 阶段 10：CLI 暴露稳定能力

### 目标

在能力稳定后再暴露 CLI，避免用户接口跟随内部设计频繁变化。

### 命令入口

项目当前入口是：

```text
understand_anything
```

不要在 plan 中混用 `cg`，除非明确新增 `[project.scripts] cg = ...`。第一版使用现有入口：

```bash
understand_anything graph build
understand_anything graph query
understand_anything graph stats
understand_anything resolve references
understand_anything sync status
understand_anything sync force
understand_anything watch
```

### 新增文件

- `src/understand_anything/cli/graph.py`
- `src/understand_anything/cli/resolve.py`
- `src/understand_anything/cli/sync.py`
- `src/understand_anything/cli/watch.py`

### 修改文件

- `src/understand_anything/cli/cli.py`
- `src/understand_anything/cli/__init__.py`
- `src/understand_anything/cli/analyze.py`

### CLI 设计要求

- 所有命令必须有 `--help`。
- 批量命令部分失败时必须非零退出。
- `--projects-dirs` 的位置必须明确：
  - 如果是 group option，只能放在子命令前。
  - 如果是 analyze/build option，应挂在具体命令上。
- 推荐把项目目录作为具体命令 option：
  ```bash
  understand_anything graph build --project-dir /path/to/project
  understand_anything graph build --project-dir /a --project-dir /b
  ```
- 不再使用容易混淆的 `--projects-dirs` 复数命名，推荐：
  ```bash
  --project-dir
  ```
  并使用 `multiple=True` 支持多次传入。

### 测试

新增：

- `tests/test_cli_graph.py`
- `tests/test_cli_resolve.py`
- `tests/test_cli_sync.py`
- `tests/test_cli_watch.py`

测试覆盖：

- help output。
- 缺参错误。
- 多 project dir。
- 一个 project 成功、一个失败时退出码为 1。
- SQLite backend option。
- JSON backend default。
- watcher 未安装 optional dependency 时错误信息明确。

## 12. 统一验收门禁

每个阶段都必须满足以下门禁：

### 代码质量

```bash
uv run ruff check src
uv run ty check src
uv run mypy src
uv run pytest
```

### 行为测试

每阶段必须新增或更新针对该阶段的测试。不能只依赖全量测试“没坏”。

### 文档

每阶段完成后更新对应文档：

- `docs/plan/codegraph_baseline_audit.md`
- `docs/plan/codegraph_incremental_plan.md`
- 如有 CLI 变更，更新 CLI 使用文档或 README 对应段落。

### 兼容

以下行为不能被无意破坏：

- 旧 JSON graph 可加载。
- 默认 backend 仍是 JSON，除非单独决策切换。
- 旧 `GraphBuilder` 基础 API 可用。
- 现有 extractor 的 functions/classes/imports/exports 不回归。
- Pipeline 可以继续在没有 SQLite / watchdog optional dependency 的环境中运行。

## 13. 推荐实施顺序

我建议严格按这个顺序做：

1. `Baseline Audit`
2. `Graph Domain Model 扩展`
3. `Python extractor 扩展`
4. `TypeScript extractor 扩展`
5. `Java extractor 扩展`
6. `C++ extractor 扩展`
7. `GraphBuilder 写入扩展节点和边`
8. `确定性跨文件引用解析`
9. `内存图查询语义`
10. `SQLite 可选后端`
11. `框架感知解析`
12. `增量同步`
13. `CLI 暴露`

如果想更保守，可以把 3-6 每个语言都作为单独 milestone。这样一旦某个 extractor 出问题，不会阻塞整个图模型演进。

## 14. 当前 plan 相比旧 plan 的关键变化

- 先加 `Baseline Audit`，避免无证据判断差距。
- 不破坏性修改 `ClassInfo.methods`。
- 跨文件解析第一版只做确定性 import-based，不做 fuzzy 写图。
- 查询语义放在 SQLite 之前。
- SQLite 是 optional backend，不直接替代 JSON。
- 框架集成必须产出明确 node/edge，不能只是 metadata。
- watcher 复用现有 fingerprint/staleness，不重建同步体系。
- CLI 使用 `understand_anything` 入口，不混用 `cg`。
- 每个阶段都有功能验收测试，不只跑四条质量命令。

