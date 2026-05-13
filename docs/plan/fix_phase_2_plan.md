# Phase 2 Fix Plan

## 背景

`docs/plan/python-core-port-plan.md` 第 2 层要求实现基础设施模块：

- `persistence/__init__.py` — 对标 `persistence/index.ts`（save/load graph, meta, fingerprints, config）
- `ignore/filter.py` — `pathspec` 替代 `ignore`
- `ignore/generator.py` — `.understandignore` 生成
- `search/fuzzy.py` — `rapidfuzz` 替代 `fuse.js`
- `search/semantic.py` — `numpy` 实现余弦相似度

当前代码已经创建这些文件并覆盖基础 happy path，但与 TypeScript core 的持久化契约、搜索 API、ignore 规则层级仍存在不等价问题。下一步修复目标是让第 2 层从“基础可用”提升到“可作为后续层稳定依赖的基础设施”。

## 总体目标

1. 保持 Python API 风格，但不得破坏与原 TypeScript core 的 JSON / 文件布局 / 行为契约。
2. 修复会影响后续图构建、增量更新、前端读取、跨版本互操作的基础设施问题。
3. 补充针对等价边界的测试，避免只测 roundtrip 导致错误契约被固化。
4. 不通过扩大 ignore/exclude 或放宽类型检查来规避问题。

## P0：Persistence 契约修复

### P0.1 保存 JSON 时使用 TS 兼容字段名

当前问题：

- `save_graph()`、`save_meta()`、`save_config()` 使用 `model_dump_json(..., by_alias=False)`。
- 写出的 JSON 字段会是 `file_path`、`node_ids`、`git_commit_hash`、`auto_update`。
- TS 契约和项目现有 JSON 边界使用 `filePath`、`nodeIds`、`gitCommitHash`、`autoUpdate`。

修复要求：

- `KnowledgeGraph`、`AnalysisMeta`、`ProjectConfig` 持久化时使用 `by_alias=True`。
- 保持 `load_*()` 能读取 camelCase JSON。
- 如果已有 snake_case 文件需要兼容，必须明确测试和实现 fallback；否则不做隐式迁移。

建议测试：

- `save_graph()` 后读取原始 JSON，断言存在 `project.gitCommitHash`、`nodes[0].filePath`、`layers[0].nodeIds`。
- 断言不存在 `git_commit_hash`、`file_path`、`node_ids`。
- `save_config()` 后断言原始 JSON 使用 `autoUpdate`。
- `save_meta()` 后断言原始 JSON 使用 `lastAnalyzedAt`、`gitCommitHash`、`analyzedFiles`。

### P0.2 对齐或兼容 TS 文件名

当前问题：

- Python 代码使用 `analysis-meta.json` 和 `project-config.json`。
- TypeScript core 使用 `.understand-anything/meta.json` 和 `.understand-anything/config.json`。
- 这会导致 Python 端读不到 TS 端已有持久化数据，也会让未来插件/前端集成出现分裂。

修复要求：

- 首选：将常量改为 TS 文件名：
  - `META_FILE = "meta.json"`
  - `CONFIG_FILE = "config.json"`
- 如需保留旧 Python 文件名，必须实现读取 fallback：
  - 优先读新契约文件名。
  - 若不存在，再读旧 Python 文件名。
  - 写入只写契约文件名，避免继续扩散旧格式。

建议测试：

- `meta_path(project_root)` 返回 `.understand-anything/meta.json`。
- `config_path(project_root)` 返回 `.understand-anything/config.json`。
- 如做 fallback，手写旧文件名数据，断言 `load_meta()` / `load_config()` 可读。

### P0.3 实现 graph filePath 脱敏/相对化

当前问题：

- TS `saveGraph()` 保存前会 sanitise file paths。
- 当前 Python `save_graph()` 直接 dump graph，可能把 `/home/.../project/src/a.py` 或外部绝对路径写入 `knowledge-graph.json`。

修复要求：

- 保存 graph 前处理所有 node 的 `filePath`：
  - 项目内绝对路径转为相对路径。
  - 项目外绝对路径只保留 basename。
  - 已经是相对路径则保持不变。
- 不应原地修改传入的 graph，除非测试明确覆盖且调用方接受。
- domain graph 目前不在第 2 层 Python 实现范围内；如果后续加入，也必须复用同一脱敏逻辑。

建议测试：

- node `filePath` 为 `project_root / "src/a.py"`，保存后 JSON 中为 `src/a.py`。
- node `filePath` 为 `/tmp/external/generated.py`，保存后 JSON 中为 `generated.py`。
- node `filePath` 为 `src/a.py`，保存后保持 `src/a.py`。
- 原始 `KnowledgeGraph` 对象不被意外修改。

### P0.4 明确 load_graph 验证语义

当前问题：

- TS `loadGraph()` 默认调用 `validateGraph()`，失败抛错；可通过 `validate: false` 跳过。
- Python 目前直接 `KnowledgeGraph.model_validate()`，解析失败返回 `None`。

修复要求：

- 需要决定 Python API 是否保留 TS 的 `validate` 选项。
- 若目标是对标 TS，应增加 `validate: bool = True` 参数：
  - `validate=True`：使用项目 schema 验证流程，失败行为需明确（抛错或返回 None）。
  - `validate=False`：只做 Pydantic 或原始 dict 加载，需与类型声明一致。

建议测试：

- 文件不存在返回 `None`。
- JSON 损坏返回 `None` 或抛错，行为固定。

## P1：Ignore 规则层级修复

### P1.1 读取 `.understand-anything/.understandignore`

当前问题：

- TS ignore-filter 的加载顺序包括 `.understand-anything/.understandignore`。
- 当前 Python 只读取项目根 `.understandignore` 和 `.gitignore`。

修复要求：

- `load_ignore_spec()` 增加读取：
  - `.understand-anything/.understandignore`
  - 项目根 `.understandignore`
- 顺序应支持后加载规则覆盖前面规则。
- 推荐顺序：
  1. 默认规则
  2. `.gitignore`（如果决定继续支持）
  3. `.understand-anything/.understandignore`
  4. 项目根 `.understandignore`

这样项目根 `.understandignore` 的 `!` 可以覆盖默认规则和 `.gitignore`。

建议测试：

- `.understand-anything/.understandignore` 中的规则生效。
- 项目根 `.understandignore` 中的 `!important.txt` 能覆盖 `.gitignore` 中的 `important.txt`。
- 默认规则仍然生效。

### P1.2 明确 `.gitignore` 支持是否属于 Python 扩展

当前问题：

- TS ignore-filter 不读取 `.gitignore`。
- Python 当前读取 `.gitignore`。
- 这可能是有用扩展，但需要明确优先级，否则 negation 行为容易与 `.understandignore` 冲突。

修复要求：

- 保留 `include_gitignore` 参数。
- 默认值为 `True`，测试必须覆盖 override 顺序。
- docstring 不得写与实际顺序相反的描述。

### P1.3 默认规则与 TS 差异检查

当前问题：

- Python 默认规则缺少或新增了一些 TS 默认规则，例如 `vendor/`、`out/`、`coverage/`、`.cache/`、`.turbo/`、`target/`、`obj/`、`*.min.js`、`*.map`、`*.generated.*`、`LICENSE`、`.gitignore` 等。
- 第 2 层要求是 pathspec 替代 ignore，不一定要求默认规则逐字一致，但“对标”时应至少知道差异。

修复要求：

- 对照 TS `DEFAULT_IGNORE_PATTERNS`，补齐核心默认规则。
- 如有 Python 特有默认规则，保留但在测试里覆盖典型项。

## P1：Search API 等价修复

### P1.4 增加 `SearchEngine` 等价类

当前问题：

- TS `search.ts` 导出 `SearchEngine`。
- 当前 Python 只提供函数式 `fuzzy_search()` / `fuzzy_search_nodes()`。
- 缺少 `types` 过滤、`nodeId` 结果契约、`updateNodes()`、`languageNotes` 搜索字段、空 query 行为。

修复要求：

- 增加 Python `SearchEngine` 类，保留 Python 命名风格可接受：
  - `__init__(nodes: list[GraphNode])`
  - `search(query: str, options: SearchOptions | None = None) -> list[SearchResult]`
  - `update_nodes(nodes: list[GraphNode]) -> None`
- 增加数据结构：
  - `SearchOptions(types: list[NodeType | str] | None = None, limit: int = 50)`
  - `SearchResult(node_id: str, score: float)`
- 搜索字段应覆盖：
  - `name`
  - `tags`
  - `summary`
  - `language_notes`
- 空白 query 返回空列表。
- 多 token query 应实现近似 TS 的 OR 语义，而不是必须整体 token_sort 匹配。

建议测试：

- 空 query 返回 `[]`。
- `types=["function"]` 只返回函数节点。
- 搜索 `languageNotes` 能命中。
- `limit` 默认 50，显式 limit 生效。
- 返回结果是 node id，不依赖对象 identity。

### P1.5 修复 `fuzzy_search_nodes()` 重复候选映射 bug

当前问题：

- `fuzzy_search_nodes()` 使用 `candidates.index(match.item)` 映射回原始节点。
- 如果两个节点 `name/summary/tags` 相同，后一个会被错误映射到第一个。

修复要求：

- 候选结构中保留原始 index 或 node id。
- 禁止用 `list.index()` 对 dict 值反查原始节点。

建议测试：

- 构造两个搜索字段完全相同但 id 不同的节点。
- 搜索结果必须能返回两个不同节点，且 id 正确。

### P1.6 分数语义需要明确

当前问题：

- TS Fuse score 是距离语义：`0 = perfect match, 1 = worst match`。
- Python `FuzzyMatch.score` 是相似度语义：`0-100` 越大越好。

修复要求：

- 如果保留函数式 API，可继续用相似度分数。
- `SearchEngine` 等价 API 应尽量返回 TS 兼容 score，或者在 docstring 明确 Python 分数语义不同。
- 推荐：`SearchEngine` 返回 `0..1` 距离分数，函数式 API 保持 `0..100` 相似度。

## P1：Semantic Search API 等价修复

### P1.7 增加 `SemanticSearchEngine` 等价类

当前问题：

- TS `embedding-search.ts` 导出 `SemanticSearchEngine`。
- 当前 Python 只有 `cosine_similarity()` 和 `search_by_embedding()`。
- 缺少 `nodeId -> embedding` 管理、`hasEmbeddings()`、`addEmbedding()`、`updateNodes()`、`types` 过滤。

修复要求：

- 增加 Python `SemanticSearchEngine` 类：
  - `__init__(nodes: list[GraphNode], embeddings: dict[str, list[float]])`
  - `has_embeddings() -> bool`
  - `add_embedding(node_id: str, embedding: Vector) -> None`
  - `search(query_embedding: Vector, options: SemanticSearchOptions | None = None) -> list[SearchResult]`
  - `update_nodes(nodes: list[GraphNode]) -> None`
- `search()` 遍历节点，按 `node.id` 查 embedding。
- 支持 `types` 过滤。
- TS 等价结果建议返回 `SearchResult(node_id, score=1 - similarity)`，并按 score 升序。

建议测试：

- `has_embeddings()` 空/非空行为。
- `add_embedding()` 后可搜索到节点。
- `types` 过滤生效。
- `update_nodes()` 后搜索只基于新节点列表。
- 缺失 embedding 的节点被跳过。

### P1.8 `search_by_embedding()` 参数校验

当前问题：

- `candidates` 长度小于 embeddings 时会在命中越界时抛 `IndexError`。
- embedding 维度不一致时依赖 numpy 抛错，错误信息不友好。

修复要求：

- 如果 `candidates is not None`，长度必须等于 `embeddings`，否则抛 `ValueError`。
- query 和 matrix 维度不一致时抛 `ValueError`，错误信息说明维度问题。

建议测试：

- candidates 长度不匹配抛 `ValueError`。
- embedding 维度不一致抛 `ValueError`。

## P2：Ignore Generator 语义整理

### P2.1 判断是否需要严格移植 TS starter generator

当前情况：

- 当前 `generate_understandignore()` 根据传入 `languages/frameworks/large_files` 生成主动生效规则。
- TS `ignore-generator.ts` 生成的是 starter 内容：扫描 `.gitignore` 和常见目录，把建议项以注释形式写出，让用户手动启用。

修复选项：

1. 严格对标 TS：
   - 增加 `generate_starter_ignore_file(project_root) -> str`。
   - 扫描 `.gitignore`、常见目录、测试文件模式。
   - 所有建议默认注释。
2. 保留 Python 当前增强版：
   - 明确命名和 docstring：这是基于语言/框架的主动规则生成器，不是 TS starter generator。
   - 可额外提供 TS 等价函数，避免功能缺口。

建议：

- 增加 TS 等价 `generate_starter_ignore_file()`。
- 保留当前 `guess_ignore_rules()` / `generate_understandignore()` 作为 Python 便利 API。

建议测试：

- 有 `.gitignore` 时，非默认规则出现在 starter 内容中且被注释。
- 存在 `tests/`、`docs/` 等目录时，starter 内容中出现对应注释建议。
- 默认已覆盖规则不重复建议。

## P2：导出与文档整理

### P2.2 更新 subpackage exports

修复后需要从以下入口导出新增类型：

- `understand_anything.search`
- `understand_anything`

新增导出候选：

- `SearchEngine`
- `SearchOptions`
- `SearchResult`
- `SemanticSearchEngine`
- `SemanticSearchOptions`
- `generate_starter_ignore_file`（如果实现）

### P2.3 Docstring 使用中文 Google 风格

AGENTS.md 要求所有接口要有中文注释，接口注释使用 Google 风格 docstring。

修复要求：

- 新增或修改 public API 时，补中文 Google 风格 docstring。
- 现有英文 docstring 可在本次修复范围内逐步改为中文，至少新增 API 不再继续扩散英文接口注释。

## 建议执行顺序

1. 修复 persistence：
   - 文件名契约
   - `by_alias=True`
   - filePath 脱敏
   - 补原始 JSON 契约测试
2. 修复 ignore filter：
   - 加 `.understand-anything/.understandignore`
   - 调整加载顺序
   - 补 negation override 测试
3. 修复 fuzzy search：
   - 修重复候选 bug
   - 增加 `SearchEngine` 等价类
   - 补类型过滤、languageNotes、空 query、nodeId 结果测试
4. 修复 semantic search：
   - 增加 `SemanticSearchEngine`
   - 补类型过滤和 embedding 管理测试
   - 给 `search_by_embedding()` 增加参数校验
5. 整理 ignore generator：
   - 选择是否严格实现 TS starter generator
   - 更新导出
6. 最后运行项目要求的四条检查命令。

## 验证命令

修复完成后必须尽力保证以下命令通过：

```bash
uv run ruff check src
uv run ty check src
uv run mypy src
uv run pytest
```

此外建议先跑第 2 层相关测试进行快速反馈：

```bash
uv run pytest tests/test_persistence.py tests/test_ignore.py tests/test_ignore_generator.py tests/test_fuzzy_search.py tests/test_semantic_search.py
```

## 完成标准

- 第 2 层五个模块仍然存在并从 package 入口正确导出。
- persistence 写出的 JSON 使用 TS 兼容 camelCase 字段。
- persistence 文件名与 TS core 对齐，或明确提供兼容 fallback。
- graph 保存不会泄露项目内/项目外绝对路径。
- ignore filter 支持默认规则、`.gitignore`（如保留）、`.understand-anything/.understandignore`、根 `.understandignore`，且 override 顺序有测试保证。
- fuzzy search 提供 TS 等价的节点搜索能力，并修复重复候选映射问题。
- semantic search 提供 TS 等价的节点 embedding 搜索能力。
- 新增 public API 有中文 Google 风格 docstring。
- 相关测试覆盖上述契约边界。
