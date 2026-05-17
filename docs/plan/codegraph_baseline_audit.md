# CodeGraph Baseline Audit

> 审计日期: 2026-05-16
> 审计方式: 代码阅读 + codegraph 工具验证, 不修改 src/

## 1. 节点类型

| 节点类型 | schema 支持 | extractor 产出 | GraphBuilder 写入 | 证据 |
|----------|------------|---------------|------------------|------|
| file | ✓ | Pipeline | `add_file`, `add_file_with_analysis` | `types.py:19`, `graph_builder.py:146` |
| function | ✓ | Python/TS/Java/C++ | `make_function_node` | `types.py:20`, `graph_builder.py:172` |
| class | ✓ | Python/TS/Java/C++ | `make_class_node` | `types.py:21`, `graph_builder.py:200` |
| method | ✗ | ✗ | ✗ | NodeType 无 METHOD 值, methods 作为 function 类型写入 |
| variable | ✓ | Python/TS | `make_variable_node` | `types.py:43`, C++和Java未实现 |
| enum | ✓ | Python/TS/C++/Java | `make_enum_node` | `types.py:44` |
| interface | ✓ | Python/TS/Java | `make_interface_node` | `types.py:45`, C++未实现 |
| type_alias | ✓ | Python/TS | `make_type_alias_node` | `types.py:46`, Java/C++未实现 |
| module | ✓ | ✗ | ✗ | `types.py:22`, 无 extractor 产出 |
| document | ✓ | Markdown parser | `add_non_code_file` | `types.py:26` |
| config | ✓ | JSON/YAML/TOML/ENV parsers | `add_non_code_file` | `types.py:25` |
| endpoint | ✓ | ✗ (extractor层) | `add_non_code_file_with_analysis` | `types.py:29`, 非代码parser产出 |
| service | ✓ | Dockerfile parser | `add_non_code_file_with_analysis` | `types.py:28` |
| resource | ✓ | Terraform parser | `add_non_code_file_with_analysis` | `types.py:32` |

**结论**: `method` 节点类型在 schema 中缺失。variable/interface/type_alias 在 C++ 和 Java extractor 中未实现。

## 2. 边类型

| 边类型 | schema 支持 | extractor 产出 | GraphBuilder 写入 | 证据 |
|--------|------------|---------------|------------------|------|
| contains | ✓ | GraphBuilder | `make_contains_edge` | `graph_builder.py:267` |
| imports | ✓ | Pipeline | `add_import_edge` | `graph_builder.py:278` |
| calls | ✓ | Pipeline (同文件) | `add_call_edge` | `graph_builder.py:289` |
| exports | ✓ | ✗ | `make_exports_edge` | `graph_builder.py:328`, 未在Pipeline中调用 |
| extends | ✗ | ✗ | `make_extends_edge` (写为 inherits) | EdgeType 无 EXTENDS, 复用 INHERITS |
| implements | ✓ | GraphBuilder | `make_implements_edge` | `graph_builder.py:315` |
| references | ✓ | ✗ | `make_references_edge` | `graph_builder.py:341` |
| type_of | ✓ | ✗ | `make_type_of_edge` | `graph_builder.py:354` |
| returns | ✓ | ✗ | `make_returns_edge` | `graph_builder.py:406` |
| instantiates | ✓ | ✗ | `make_instantiates_edge` | `graph_builder.py:393` |
| overrides | ✓ | ✗ | `make_overrides_edge` | `graph_builder.py:367` |
| decorates | ✓ | ✗ | `make_decorates_edge` | `graph_builder.py:380` |

**结论**: exports/extends/references/type_of/returns/instantiates/overrides/decorates 边工厂函数已定义, 但未在 Pipeline 中实际调用。

## 3. 解析能力

| 能力 | 实现状态 | 证据 |
|------|---------|------|
| 同文件调用 | ✓ 已实现 | `pipeline.py:_resolve_and_add_calls` |
| 跨文件 import 解析 | ✓ 已实现 | `pipeline.py:_resolve_and_add_imports` |
| 跨文件 calls 解析 | △ 部分实现 | `pipeline.py:_resolve_cross_file_references`, 含模糊匹配 |
| class method 调用解析 | ✓ 已实现 | 在 `_resolve_and_add_calls` 中 |
| constructor 调用解析 | ✗ 未实现 | Java 识别 `new` 但不解析为跨文件边 |
| builtin/stdlib 过滤 | ✓ 已实现 | `resolution/builtins.py`, 4种语言 |
| re-export/barrel 解析 | ✓ 已实现 | `resolution/import_resolver.py:trace_reexport_chain` |
| alias import 解析 | △ 部分实现 | Python `import X as Y` 已处理, 跨文件alias未追踪 |

**关键问题**: 跨文件解析包含 4 层策略 (框架→导入→名称→模糊), 其中模糊解析 (confidence 0.3-0.5) 也写入主图。v2 plan 要求第一版只写入 confidence ≥ 0.9 的边。

## 4. 存储与查询

| 能力 | 实现状态 | 证据 |
|------|---------|------|
| JSON graph 保存/读取 | ✓ 已实现 | `persistence/__init__.py:save_graph/load_graph` |
| graph validation | ✓ 已实现 | `schema.py:validate_graph` |
| SQLite 存储 | ✓ 已实现 | `persistence/sqlite_backend.py` |
| FTS5 全文搜索 | ✓ 已实现 | `persistence/queries.py:search_fts` |
| DatabaseBackend 统一包装 | ✓ 已实现 | `persistence/__init__.py:DatabaseBackend` |
| callers/callees 查询 | ✓ 已实现 | `analysis/graph_traversal.py` |
| path finding | ✓ 已实现 | `analysis/graph_traversal.py:find_path` |
| impact analysis | ✓ 已实现 | `analysis/graph_traversal.py:get_impact` |
| fuzzy search | ✓ 已实现 | `search/fuzzy.py` |
| semantic search | ✓ 已实现 | `search/semantic.py` |

**关键问题**: DatabaseBackend 将 JSON 和 SQLite 包装在单一类中, v2 plan 要求保持两个后端独立。

## 5. 框架集成

| 能力 | 实现状态 | 证据 |
|------|---------|------|
| 框架检测 | ✓ | `pipeline.py:_detect_frameworks`, 10个框架配置 |
| 框架名称写入 metadata | ✓ | `builder.set_frameworks()`, 只写 display_name 字符串 |
| 框架感知图节点 | ✗ | 检测到 FastAPI 不产生 endpoint node |
| 框架感知图边 | ✗ | 检测到 React 不产生 component references 边 |

## 6. 增量同步

| 能力 | 实现状态 | 证据 |
|------|---------|------|
| fingerprint 计算 | ✓ | `analysis/fingerprint.py` |
| staleness 检查 | ✓ | `analysis/staleness.py` |
| change classification | ✓ | `analysis/change_classifier.py` |
| watchdog 文件监听 | ✓ | `sync/watcher.py` |
| 增量同步协调 | △ | `sync/index.py` 存在但未使用 fingerprint/staleness |
| watcher 复用现有模块 | ✗ | watcher 独立实现, 未用 staleness/change_classifier |

## 7. CLI

| 能力 | 实现状态 | 证据 |
|------|---------|------|
| analyze 命令 | ✓ | `cli/analyze.py` |
| graph build 命令 | ✓ | `cli/graph.py` |
| graph query/stats 命令 | ✓ | `cli/graph.py` |
| resolve 命令 | ✓ | `cli/resolve.py` |
| watch 命令 | ✓ | `cli/watch.py` |
| 入口命名 | ✗ | 代码使用 `cg`, 应为 `understand_anything` |
| --project-dir | ✗ | 使用 `--projects-dirs` 复数形式 |

## 8. 破坏性变更清单

| 变更 | 状态 | 影响 |
|------|------|------|
| `ClassInfo.methods: list[str]` → `list[MethodInfo]` | **已实施** | 25个测试修改, 旧代码不兼容 |
| `EdgeType` 新增 6 个值 | 已实施 | 向后兼容 (Enum 扩展) |
| `NodeType` 新增 4 个值 | 已实施 | 向后兼容 (Enum 扩展) |
| `StructuralAnalysis` 新增 4 字段 | 已实施 | 向后兼容 (默认空列表) |

## 9. 待修正项 (按优先级)

1. **回滚 `ClassInfo.methods` 类型** — 恢复 `list[str]`, 新增 `method_details: list[MethodInfo]`
2. **DatabaseBackend 拆分** — 独立 JSON 和 SQLite 后端, pipeline 层选择
3. **跨文件解析去模糊** — 移除模糊匹配写入, 只做 confidence ≥ 0.9 的确定性解析
4. **Watcher 接入 staleness** — 复用 fingerprint/change_classifier/staleness 模块
5. **CLI 命名统一** — `understand_anything` 入口, `--project-dir` 选项
6. **框架产出 graph 增益** — FastAPI/Django/React/Spring 产出 node/edge
