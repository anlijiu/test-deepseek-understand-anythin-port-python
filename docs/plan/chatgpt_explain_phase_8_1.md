

-------------------

这里的“端到端集成测试（完整图构建管道）”通常指：

> 不再测试某个单独函数、模块，而是从“输入源码仓库”开始，一直到“最终生成 Graph / GraphRAG 数据”结束，完整跑一遍整个系统，并验证结果正确。

对于 [Understand-Anything](https://github.com/Lum1104/Understand-Anything?utm_source=chatgpt.com) 这种项目来说，“图构建管道（graph build pipeline）”一般会包含：

1. 扫描代码仓库
2. 解析源码（tree-sitter / AST）
3. 提取实体

   * 文件
   * 类
   * 函数
   * import
   * 调用关系
4. 构建关系图
5. 写入图数据库 / 中间 JSON
6. 生成 embedding / chunk
7. 建立 GraphRAG 索引
8. 最终可查询

而“端到端集成测试”就是：

* 给一个固定测试仓库
* 自动执行整条 pipeline
* 验证最终结果

而不是只测：

* parser 对不对
* AST 对不对
* 某个 extractor 对不对

---

# 举个具体例子

假设你正在把 TS 版移植到 Python。

你可能已经有：

```text
PythonParser
SymbolExtractor
CallGraphBuilder
Neo4jWriter
EmbeddingIndexer
```

单元测试可能是：

```python
def test_extract_function():
    code = "def foo(): pass"
    result = extractor.extract(code)
    assert result.name == "foo"
```

但这不代表整个系统能工作。

---

真正的 E2E（End-to-End）测试会像：

```text
tests/fixtures/simple_repo/
    main.py
    utils.py
```

测试：

```python
def test_full_pipeline():
    graph = build_graph_from_repo("fixtures/simple_repo")

    assert graph.has_node("main.foo")
    assert graph.has_node("utils.bar")

    assert graph.has_edge(
        "main.foo",
        "utils.bar",
        type="CALLS"
    )
```

这才是：

# “完整图构建管道”测试

---

# 为什么这种测试很重要

因为 GraphRAG / code graph 系统：

## 最大问题不是单模块

而是：

```text
parser -> extractor -> normalizer
-> graph builder -> serializer
-> embedding -> indexer
```

之间：

* schema 不一致
* ID 不一致
* 路径丢失
* 名字 canonicalization 出错
* 增量更新错
* relation 丢失
* 多语言 merge 错

这些问题：

单元测试根本测不出来。

---

# 在 Understand-Anything 这种项目里

尤其容易出问题的是：

## 1. cross-language graph

比如：

```text
Python -> C++ binding
TS -> backend API
Rust -> ffi
```

节点 ID 是否一致。

---

## 2. 增量更新

第一次：

```text
repo -> graph
```

第二次：

```text
repo changed -> incremental update
```

图是否一致。

---

## 3. tree-sitter 差异

TS 版：

```ts
node.childForFieldName()
```

Python binding：

```python
node.child_by_field_name()
```

行为可能不同。

导致：

* 漏节点
* range 错误
* parent 错误

只有 E2E 才能发现。

---

# 一般会验证什么

完整图构建 E2E 常见断言：

## 图规模

```python
assert graph.node_count == 128
assert graph.edge_count == 432
```

---

## 特定节点存在

```python
assert graph.has_node("UserService.login")
```

---

## 特定关系存在

```python
assert graph.has_edge(
    "Controller.login",
    "UserService.login",
    type="CALLS"
)
```

---

## Graph schema 正确

```python
assert node["kind"] == "function"
assert edge["type"] == "IMPORTS"
```

---

## serialization 稳定

比如：

```python
snapshot == expected_snapshot.json
```

这类叫：

# golden test / snapshot test

你前面提到的 “golden-data 测试” 本质上就是这个。

---

# 在 Python 移植阶段

建议至少做 3 层：

## 第一层：Parser 单测

```text
源码 -> AST
```

---

## 第二层：Extractor 集成测试

```text
AST -> symbols/relations
```

---

## 第三层：E2E Graph Pipeline

```text
repo -> final graph
```

这是最重要的。

---

# 推荐目录结构

```text
tests/
├── fixtures/
│   ├── small_python_repo/
│   ├── ts_mixed_repo/
│   └── cpp_repo/
│
├── expected/
│   ├── small_python_repo.graph.json
│   └── ...
│
├── test_parser.py
├── test_extractors.py
└── test_e2e_pipeline.py
```

---

# 一个非常关键的实践

很多 GraphRAG 项目最终都会加：

# “Graph Snapshot Regression Test”

即：

```text
输入 repo 固定
输出 graph json 固定
```

CI 中：

```text
新 graph == 旧 graph
```

否则失败。

因为：

Graph 系统特别容易：

* 重构后 silently break
* relation 少一部分
* canonical name 变化
* hash 改变
* node id 漂移

但系统表面还能跑。

---

# 你这个项目里，我会重点建议测试：

## 1. graph canonicalization

因为 TS -> Python 最容易漂。

---

## 2. stable node id

否则增量更新会炸。

---

## 3. multi-language consistency

如果未来支持：

* Python
* TS
* C++
* Rust

这个尤其重要。

---

# 简单一句话总结

“端到端集成测试（完整图构建管道）”就是：

> 用真实代码仓库作为输入，完整运行：
>
> 解析 → 提取 → 构图 → 序列化 → 索引
>
> 然后验证最终 graph/GraphRAG 结果是否正确且稳定。
