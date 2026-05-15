
## 背景

项目当前状态：所有核心库模块（类型、模式验证、图构建、插件系统、提取器、解析器、持久化、忽略过滤、搜索、层级检测、导览生成等）均已实现并通过 727 个单元测试。但是缺少一个将各模块串联起来的**编排层（Pipeline）**和**端到端集成测试**。

目标：创建一个 `Pipeline` 编排类，将完整管道串联起来，然后编写集成测试验证整个流程的正确性。

---

## 实现计划

### 步骤 1：创建 `PipelineResult` 数据类

**文件**：`src/understand_anything/pipeline.py`（新文件）

```python
@dataclass
class PipelineResult:
    graph: KnowledgeGraph
    validation: ValidationResult
    layers: list[Layer]
    tour: list[TourStep]
    analyzed_files: int
    ignored_files: int
    fingerprints: dict[str, str]  # file_path -> SHA-256 hex
    meta: AnalysisMeta
```

---

### 步骤 2：实现 `Pipeline` 类

**文件**：`src/understand_anything/pipeline.py`

#### 构造函数

```python
class Pipeline:
    def __init__(
        self,
        project_root: str | Path,
        *,
        git_hash: str | None = None,
        language_registry: LanguageRegistry | None = None,
        plugin_registry: PluginRegistry | None = None,
        include_gitignore: bool = True,
        include_understandignore: bool = True,
        enable_validation: bool = True,
        enable_layer_detection: bool = True,
        enable_tour_generation: bool = True,
        enable_persistence: bool = True,
    ) -> None:
```

- 如果 `plugin_registry` 未提供，自动创建并注册 TreeSitterPlugin + 所有 12 个非代码解析器
- 如果 `language_registry` 未提供，创建默认 LanguageRegistry
- `git_hash` 未提供时通过 `subprocess` 调用 `git rev-parse HEAD` 自动检测

#### 核心方法 `run()`

完整管道流程：

```
1. _discover_files()          → 递归扫描项目目录，排除 .understand-anything/
2. _filter_ignored()          → 加载 .gitignore/.understandignore，过滤文件
3. 对每个文件:
   a. 读取内容（跳过二进制文件）
   b. registry.analyze_file()  → StructuralAnalysis
   c. _process_code_file()     → builder.add_file_with_analysis()
      或 _process_non_code_file() → builder.add_non_code_file_with_analysis()
   d. 解析 import → add_import_edge()
   e. 解析 call graph → add_call_edge()
4. builder.build()            → KnowledgeGraph
5. validate_graph()           → ValidationResult
6. detect_layers()            → list[Layer]（启发式）
7. generate_heuristic_tour()  → list[TourStep]
8. _compute_fingerprints()    → dict[str, str]
9. save_graph/ save_meta / save_fingerprints  → 持久化
10. 返回 PipelineResult
```

#### 关键辅助方法

| 方法 | 功能 |
|------|------|
| `_discover_files()` | `Path.rglob(\"*\")` 递归扫描，排除目录和 `.understand-anything/` |
| `_filter_ignored()` | 调用 `load_ignore_spec()` + `filter_files()` |
| `_read_file()` | 尝试 UTF-8，失败尝试 latin-1，都失败则跳过（二进制文件） |
| `_process_code_file()` | 启发式判断复杂度，生成摘要，调用 builder |
| `_process_non_code_file()` | 根据分析内容推断 node_type，调用 builder |
| `_resolve_node_type()` | document/config/schema/pipeline/resource 推断逻辑 |
| `_detect_complexity()` | 0-2 函数→simple, 3-8→moderate, 9+→complex |
| `_compute_fingerprints()` | SHA-256 内容哈希 |
| `_detect_git_hash()` | `git rev-parse HEAD`，失败返回 \"unknown\" |

#### Import 边解析注意事项

- `TreeSitterPlugin.resolve_imports()` 返回绝对路径的 `ImportResolution`
- Pipeline 需要用 `os.path.relpath()` 转回项目相对路径
- 只为目标文件已在项目中且已被分析的文件创建 import 边
- TypeScript 的 `./utils` 能正确解析；Python 的 `from src.utils import helper` 需要额外处理（已知限制，后续改进）

---

### 步骤 3：创建测试夹具

**文件**：`tests/test_integration/conftest.py`（新文件）

创建 3 个夹具工厂函数，使用 pytest 的 `tmp_path` 动态创建迷你项目：

#### 3a. `mini_python_project`

```
mini-python/
  src/
    __init__.py          (空)
    main.py              (函数: main, load_data, process_data，导入 utils)
    utils.py             (函数: helper, validate)
    models/
      __init__.py        (空)
      user.py            (类: User，方法: greet, to_dict)
  tests/
    test_main.py         (函数: test_main)
  README.md              (Markdown 文档)
  config.yaml            (YAML 配置)
  Makefile               (构建目标)
  .gitignore             (忽略 *.log, __pycache__/)
```

#### 3b. `mini_typescript_project`

```
mini-ts/
  src/
    index.ts             (导入 ./utils 的 greet, 定义 main 函数)
    utils.ts             (导出 greet, add 函数)
  tsconfig.json          (JSON 配置)
```

#### 3c. `mini_configs_project`

```
mini-configs/
  docker-compose.yml     (services: web, db)
  schema.sql             (CREATE TABLE users, posts)
  schema.graphql         (Query: user, users)
  main.tf                (resource: aws_s3_bucket, aws_dynamodb_table)
  .env                   (DATABASE_URL, DEBUG)
  Dockerfile             (FROM python:3.11-slim)
  script.sh              (echo \"Hello, World!\")
```

---

### 步骤 4：编写集成测试

**文件**：`tests/test_integration/test_complete_pipeline.py`（新文件）

#### 8 个测试场景

| # | 测试场景 | 验证点 |
|---|---------|--------|
| 1 | **完整管道 — Python 项目** | 文件节点数、函数/类节点、contains 边、语言检测、验证通过、层级生成、导览生成 |
| 2 | **完整管道 — TypeScript 项目** | TS 文件正确解析、import 边创建 |
| 3 | **纯非代码项目** | 非代码文件节点正确创建、各类型子节点（service/table/endpoint/resource） |
| 4 | **忽略过滤** | `.gitignore` 中的 `*.log` 文件不出现在图中 |
| 5 | **持久化** | 图/元数据/指纹文件写入磁盘、可重新加载、加载后节点数一致 |
| 6 | **阶段开关** | `enable_*=False` 时对应阶段跳过 |
| 7 | **空项目** | 生成空图不崩溃 |
| 8 | **二进制文件容错** | 无法解析的二进制文件被跳过，管道继续运行 |

---

### 步骤 5：更新导出

**文件**：`src/understand_anything/__init__.py`

添加：
```python
from understand_anything.pipeline import Pipeline, PipelineResult
```

**文件**：`tests/test_integration/__init__.py`（新建空文件）

---

## 关键设计决策

1. **Pipeline 放在 `src/understand_anything/pipeline.py`**（顶层）而非 `analysis/` 下，因为 Pipeline 编排了所有模块（插件、持久化、忽略、分析），是事实上的顶层入口
2. **不使用 LLM**：集成测试中的 pipeline 仅使用启发式方法（`detect_layers`、`generate_heuristic_tour`），不依赖外部 LLM API
3. **路径规范化**：所有文件路径在内部统一使用 POSIX 风格（`Path.as_posix()`），保证跨平台一致性
4. **Import 解析的已知限制**：Python 的 `from src.utils import helper` 使用模块路径而非文件路径，当前 `resolve_imports` 对这种情况支持有限，TypeScript 的 `./utils` 相对路径导入能正确解析

---

## 验证步骤

实现完成后按顺序执行：

```bash
uv run ruff check src              # Lint 检查
uv run ty check src                # ty 类型检查
uv run mypy src                    # mypy 严格模式类型检查
uv run pytest tests/test_integration/ -v  # 集成测试
uv run pytest                      # 全量测试（727 已有 + 新增）
```

预计新增代码量：约 450 行（Pipeline 类 ~250 行 + 集成测试 ~200 行）
