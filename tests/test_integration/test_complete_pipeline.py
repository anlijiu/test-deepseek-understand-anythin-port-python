"""端到端集成测试 — 完整 Pipeline 图构建管道.

验证 Pipeline 类将文件发现、忽略过滤、分析、图构建、验证、
层级检测、导览生成、指纹计算和持久化正确串联.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from understand_anything.persistence import (
    fingerprints_path,
    graph_path,
    load_fingerprints,
    load_graph,
    load_meta,
    meta_path,
)
from understand_anything.pipeline import Pipeline, PipelineResult
from understand_anything.types import NodeType

if TYPE_CHECKING:
    from understand_anything.types import KnowledgeGraph


def _assert_no_dangling_edges(graph: KnowledgeGraph) -> None:
    """验证图中每条边的 source 和 target 都对应一个存在的节点."""
    node_ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        assert edge.source in node_ids, (
            f"Dangling edge source: {edge.source} -> {edge.target}"
        )
        assert edge.target in node_ids, (
            f"Dangling edge target: {edge.source} -> {edge.target}"
        )


# ===========================================================================
# Test 1: Complete pipeline — Python project
# ===========================================================================


def test_complete_pipeline_python(mini_python_project: Path) -> None:
    """验证对 Python 项目的完整管道执行."""
    pipeline = Pipeline(mini_python_project)
    result = pipeline.run()

    assert isinstance(result, PipelineResult)
    graph = result.graph

    # 应该有文件节点（.py + README.md + config.yaml + Makefile + .gitignore）
    file_nodes = [n for n in graph.nodes if n.type == NodeType.FILE]
    assert len(file_nodes) >= 4, f"Expected >=4 file nodes, got {len(file_nodes)}"

    # 应该有函数节点（main, load_data, process_data, helper, validate, greet, to_dict, test_main）
    function_nodes = [n for n in graph.nodes if n.type == NodeType.FUNCTION]
    assert len(function_nodes) >= 3, f"Expected >=3 function nodes, got {len(function_nodes)}"

    # 应该有类节点（User）
    class_nodes = [n for n in graph.nodes if n.type == NodeType.CLASS]
    assert len(class_nodes) >= 1, f"Expected >=1 class node, got {len(class_nodes)}"

    # 应该有 contains 边（文件 → 函数/类）
    contains_edges = [e for e in graph.edges if e.type == "contains"]
    assert len(contains_edges) >= 4, f"Expected >=4 contains edges, got {len(contains_edges)}"

    # 应该检测到 Python 语言
    assert "python" in graph.project.languages

    # 验证应该通过
    assert result.validation.success, f"Validation failed: {result.validation.errors}"

    # 应该有层级
    assert len(result.layers) > 0, f"Expected layers, got {len(result.layers)}"

    # 应该有导览步骤
    assert len(result.tour) > 0, f"Expected tour steps, got {len(result.tour)}"

    # layers 和 tour 应写回到 result.graph
    assert len(result.graph.layers) == len(result.layers), (
        f"graph.layers ({len(result.graph.layers)}) != result.layers ({len(result.layers)})"
    )
    assert len(result.graph.tour) == len(result.tour), (
        f"graph.tour ({len(result.graph.tour)}) != result.tour ({len(result.tour)})"
    )

    # 统计信息
    assert result.analyzed_files >= 4
    assert result.ignored_files >= 0

    # 无悬空边
    _assert_no_dangling_edges(graph)


# ===========================================================================
# Test 2: Complete pipeline — TypeScript project
# ===========================================================================


def test_complete_pipeline_typescript(mini_typescript_project: Path) -> None:
    """验证对 TypeScript 项目的完整管道执行.

    强制 importer-before-importee 文件发现顺序，验证 import 边创建
    不依赖于文件系统遍历顺序.
    """

    class OrderedPipeline(Pipeline):
        def _discover_files(self) -> list[Path]:
            # 强制 importer 排在 importee 前面 — 最容易触发顺序依赖回归
            return [
                Path("src/index.ts"),
                Path("src/utils.ts"),
                Path("tsconfig.json"),
            ]

    pipeline = OrderedPipeline(mini_typescript_project)
    result = pipeline.run()

    assert result.validation.success, f"Validation failed: {result.validation.errors}"

    graph = result.graph

    # 文件节点
    file_nodes = [n for n in graph.nodes if n.type == NodeType.FILE]
    assert len(file_nodes) >= 2, f"Expected >=2 file nodes, got {len(file_nodes)}"

    # 函数节点（main, greet, add）
    function_nodes = [n for n in graph.nodes if n.type == NodeType.FUNCTION]
    assert len(function_nodes) >= 3, f"Expected >=3 function nodes, got {len(function_nodes)}"

    # TypeScript 语言检测
    assert "typescript" in graph.project.languages

    # 精确断言 import 边
    import_edges = [
        (e.source, e.target)
        for e in graph.edges
        if e.type == "imports"
    ]
    assert ("file:src/index.ts", "file:src/utils.ts") in import_edges, (
        f"Expected import edge file:src/index.ts -> file:src/utils.ts,"
        f" got {import_edges}"
    )

    # 层级和导览
    assert len(result.layers) > 0, f"Expected layers, got {len(result.layers)}"
    assert len(result.tour) > 0, f"Expected tour steps, got {len(result.tour)}"

    # 无悬空边
    _assert_no_dangling_edges(graph)


@pytest.mark.parametrize(
    "discovery_order",
    (
        # importer 在前，importee 在后
        (Path("src/index.ts"), Path("src/utils.ts"), Path("tsconfig.json")),
        # importee 在前，importer 在后
        (Path("src/utils.ts"), Path("src/index.ts"), Path("tsconfig.json")),
    ),
    ids=["importer-first", "importee-first"],
)
def test_import_edge_order_independent(
    mini_typescript_project: Path, discovery_order: tuple[Path, ...]
) -> None:
    """验证 import 边创建不依赖于文件发现顺序.

    无论 _discover_files() 返回的 importer 在 importee 之前还是之后，
    最终图都应包含正确的 import 边.
    """

    class OrderedPipeline(Pipeline):
        def _discover_files(self) -> list[Path]:
            return list(discovery_order)

    pipeline = OrderedPipeline(mini_typescript_project)
    result = pipeline.run()

    assert result.validation.success, f"Validation failed: {result.validation.errors}"

    # 精确断言 import 边
    import_edges = [
        (e.source, e.target)
        for e in result.graph.edges
        if e.type == "imports"
    ]
    assert ("file:src/index.ts", "file:src/utils.ts") in import_edges, (
        f"Expected import edge file:src/index.ts -> file:src/utils.ts,"
        f" got {import_edges}"
    )


def test_import_edge_to_non_code_file(tmp_path: Path) -> None:
    """验证 import 边指向非代码文件时使用正确的节点 ID.

    TypeScript side-effect import ``import "./styles.css"`` 应生成一条
    指向 ``document:src/styles.css`` 的边，而不是指向不存在的
    ``file:src/styles.css``.
    """
    root = tmp_path / "ts-css-import"
    root.mkdir(parents=True, exist_ok=True)
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)

    (src / "index.ts").write_text(
        'import "./styles.css";\n\n'
        "function main(): void {}\n"
    )
    (src / "styles.css").write_text("body { margin: 0; }\n")

    class OrderedPipeline(Pipeline):
        def _discover_files(self) -> list[Path]:
            # 故意让 importer 排在 importee 前面，以前会静默丢失这条边
            return [Path("src/index.ts"), Path("src/styles.css")]

    pipeline = OrderedPipeline(root)
    result = pipeline.run()

    assert result.validation.success, f"Validation failed: {result.validation.errors}"

    import_edges = [
        (e.source, e.target)
        for e in result.graph.edges
        if e.type == "imports"
    ]
    assert ("file:src/index.ts", "document:src/styles.css") in import_edges, (
        f"Expected import edge file:src/index.ts -> document:src/styles.css,"
        f" got {import_edges}"
    )

    # 确认 document 节点存在
    node_ids = {n.id for n in result.graph.nodes}
    assert "document:src/styles.css" in node_ids, (
        f"Expected document:src/styles.css node, got {node_ids}"
    )


# ===========================================================================
# Test 3: Pure non-code project (configs, schemas, infra)
# ===========================================================================


def test_complete_pipeline_non_code(mini_configs_project: Path) -> None:
    """验证纯非代码项目的管道执行."""
    pipeline = Pipeline(mini_configs_project)
    result = pipeline.run()

    assert result.validation.success, f"Validation failed: {result.validation.errors}"

    graph = result.graph

    # 节点类型应该是非代码类型
    node_types = {n.type for n in graph.nodes}
    # 应该包含 config, schema, pipeline, resource 等
    non_file_code_types = node_types - {NodeType.FILE, NodeType.FUNCTION, NodeType.CLASS}
    assert len(non_file_code_types) >= 2, (
        f"Expected non-code node types, got {node_types}"
    )

    # 应该有 service 子节点（Dockerfile 中的 FROM image）
    service_nodes = [n for n in graph.nodes if n.type == NodeType.SERVICE]
    assert len(service_nodes) >= 1, (
        f"Expected >=1 service node from Dockerfile, got {len(service_nodes)}"
    )

    # 应该有 table 子节点（schema.sql）
    table_nodes = [n for n in graph.nodes if n.type == NodeType.TABLE]
    assert len(table_nodes) >= 2, (
        f"Expected >=2 table nodes from schema.sql, got {len(table_nodes)}"
    )

    # 应该有 endpoint 子节点（schema.graphql 的 Query）
    endpoint_nodes = [n for n in graph.nodes if n.type == NodeType.ENDPOINT]
    assert len(endpoint_nodes) >= 2, (
        f"Expected >=2 endpoint nodes from schema.graphql, got {len(endpoint_nodes)}"
    )

    # 应该有 resource 子节点（main.tf）
    resource_nodes = [n for n in graph.nodes if n.type == NodeType.RESOURCE]
    assert len(resource_nodes) >= 2, (
        f"Expected >=2 resource nodes from main.tf, got {len(resource_nodes)}"
    )

    # 统计信息
    assert result.analyzed_files >= 6

    # 纯非代码项目可能没有架构层级，但导览应正常生成
    assert len(result.tour) > 0, f"Expected tour steps, got {len(result.tour)}"

    # 无悬空边
    _assert_no_dangling_edges(graph)


# ===========================================================================
# Test 4: Ignore filtering
# ===========================================================================


def test_ignore_filtering(tmp_path: Path) -> None:
    """验证 .gitignore 规则正确过滤文件."""
    root = tmp_path / "filtered-project"
    root.mkdir(parents=True)

    # 创建源文件
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hello')\n")
    (root / "src" / "utils.py").write_text("def helper():\n    pass\n")

    # 创建应该被忽略的文件
    (root / "debug.log").write_text("log data\n")
    (root / "error.log").write_text("error data\n")

    # 创建 .gitignore
    (root / ".gitignore").write_text("*.log\n")

    pipeline = Pipeline(root)
    result = pipeline.run()

    assert result.validation.success

    # .log 文件不应出现在图中
    graph = result.graph
    file_paths = [n.file_path for n in graph.nodes if n.file_path is not None]
    assert "debug.log" not in file_paths, f"debug.log should be ignored, but found in {file_paths}"
    assert "error.log" not in file_paths, f"error.log should be ignored, but found in {file_paths}"

    # .py 文件应该在图中
    assert "src/main.py" in file_paths
    assert "src/utils.py" in file_paths

    # 被忽略文件计数
    assert result.ignored_files >= 2, f"Expected >=2 ignored files, got {result.ignored_files}"

    # 无悬空边
    _assert_no_dangling_edges(graph)


# ===========================================================================
# Test 5: Persistence (save + reload)
# ===========================================================================


def test_persistence(mini_python_project: Path) -> None:
    """验证图/元数据/指纹的持久化和重新加载."""
    pipeline = Pipeline(mini_python_project, enable_persistence=True)
    result = pipeline.run()

    # 验证文件已写入
    gf = graph_path(mini_python_project)
    assert gf.is_file(), f"Graph file not written at {gf}"

    mf = meta_path(mini_python_project)
    assert mf.is_file(), f"Meta file not written at {mf}"

    ff = fingerprints_path(mini_python_project)
    assert ff.is_file(), f"Fingerprints file not written at {ff}"

    # 重新加载图
    reloaded = load_graph(mini_python_project)
    assert reloaded is not None, "Failed to reload graph"
    assert len(reloaded.nodes) == len(result.graph.nodes), (
        f"Node count mismatch: {len(reloaded.nodes)} vs {len(result.graph.nodes)}"
    )

    # 持久化的图应包含非空的 layers 和 tour
    assert len(reloaded.layers) == len(result.layers), (
        f"Persisted layers count mismatch: {len(reloaded.layers)} vs {len(result.layers)}"
    )
    assert len(reloaded.layers) > 0, "Persisted layers should be non-empty"
    assert len(reloaded.tour) == len(result.tour), (
        f"Persisted tour count mismatch: {len(reloaded.tour)} vs {len(result.tour)}"
    )
    assert len(reloaded.tour) > 0, "Persisted tour should be non-empty"

    # 重新加载元数据
    meta = load_meta(mini_python_project)
    assert meta is not None
    assert meta.analyzed_files == result.analyzed_files

    # 重新加载指纹
    fps = load_fingerprints(mini_python_project)
    assert len(fps) > 0
    assert len(fps) == len(result.fingerprints)


# ===========================================================================
# Test 6: Stage toggles
# ===========================================================================


def test_stage_toggles_disabled(mini_python_project: Path) -> None:
    """验证当 enable_*=False 时对应阶段被跳过."""
    pipeline = Pipeline(
        mini_python_project,
        enable_validation=False,
        enable_layer_detection=False,
        enable_tour_generation=False,
        enable_persistence=False,
    )
    result = pipeline.run()

    # 验证应标记为成功（未运行）
    assert result.validation.success
    assert result.validation.errors == [] or result.validation.errors is None

    # 层级应为空
    assert result.layers == []

    # 导览应为空
    assert result.tour == []

    # 元数据应为 None（未持久化）
    assert result.meta is None

    # 图仍然被构建
    assert len(result.graph.nodes) > 0


def test_stage_toggles_partial(mini_python_project: Path) -> None:
    """验证部分禁用阶段时管道正常运行."""
    # 仅启用验证和图构建
    pipeline = Pipeline(
        mini_python_project,
        enable_layer_detection=False,
        enable_tour_generation=False,
        enable_persistence=False,
        enable_validation=True,
    )
    result = pipeline.run()

    # 验证通过
    assert result.validation.success

    # 层级和导览跳过
    assert result.layers == []
    assert result.tour == []

    # 图被构建
    assert len(result.graph.nodes) > 0


# ===========================================================================
# Test 7: Empty project
# ===========================================================================


def test_empty_project(tmp_path: Path) -> None:
    """验证空项目不崩溃，生成空图."""
    root = tmp_path / "empty-project"
    root.mkdir(parents=True)

    pipeline = Pipeline(root)
    result = pipeline.run()

    # 应该正常返回
    assert isinstance(result, PipelineResult)

    # 图应该为空
    graph = result.graph
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0

    # 空图的验证会失败（没有节点），但管道不应崩溃
    assert not result.validation.success

    # 统计信息
    assert result.analyzed_files == 0
    assert result.ignored_files == 0


# ===========================================================================
# Test 8: Binary file tolerance
# ===========================================================================


def test_binary_file_tolerance(tmp_path: Path) -> None:
    """验证二进制文件被跳过，不导致管道崩溃."""
    root = tmp_path / "binary-project"
    root.mkdir(parents=True)

    # 创建有效的 Python 文件
    (root / "main.py").write_text("print('hello')\n")

    # 创建一个二进制文件
    binary_content = bytes(range(256))  # 包含不可解码的字节
    (root / "data.bin").write_bytes(binary_content)

    # 创建一个包含 null 字节的 "文本" 文件
    (root / "corrupt.txt").write_bytes(b"some text\x00\x00\x01\x02binary")

    pipeline = Pipeline(root)
    result = pipeline.run()

    # 管道不应崩溃
    assert isinstance(result, PipelineResult)

    # main.py 应该被分析
    graph = result.graph
    file_paths = [n.file_path for n in graph.nodes if n.file_path is not None]
    assert "main.py" in file_paths

    # 二进制文件（含 null 字节）不应出现在图中
    assert "data.bin" not in file_paths
    assert "corrupt.txt" not in file_paths

    # analyzed_files 应该只计算成功解析的文件
    assert result.analyzed_files >= 1

    # 无悬空边
    _assert_no_dangling_edges(graph)


def test_class_method_nodes_and_call_edges(tmp_path: Path) -> None:
    """验证类方法创建了 function:{file}:{method} 节点，且方法间调用边正确.

    GraphBuilder 应为每个类方法创建独立节点，Pipeline 应将同文件内
    的方法间调用解析为 call 边. 即使 validation 关闭也不应产生悬空边.
    """
    root = tmp_path / "class-methods"
    root.mkdir(parents=True)

    (root / "main.py").write_text("""class Calculator:
    def add(self, a: int, b: int) -> int:
        result = a + b
        self.log(result)
        return result

    def log(self, value: int) -> None:
        print(f"Result: {value}")


def main() -> None:
    calc = Calculator()
    calc.add(1, 2)
""")

    # 关闭 validation 以验证原始图也不含悬空边
    pipeline = Pipeline(root, enable_validation=False)
    result = pipeline.run()

    graph = result.graph

    # 应该有类节点
    class_nodes = [n for n in graph.nodes if n.type == NodeType.CLASS]
    assert len(class_nodes) == 1

    # 应该有方法节点（add, log）
    method_nodes = [
        n for n in graph.nodes
        if n.type == NodeType.FUNCTION and "Calculator" not in n.name
    ]
    method_names = {n.name for n in method_nodes}
    assert "add" in method_names, f"Expected 'add' method node, got {method_names}"
    assert "log" in method_names, f"Expected 'log' method node, got {method_names}"

    # 方法节点应通过 contains 边挂在类节点下
    class_id = class_nodes[0].id
    method_contains = [
        e for e in graph.edges
        if e.type == "contains" and e.source == class_id
    ]
    assert len(method_contains) >= 2, (
        f"Expected >=2 contains edges from class to methods, got {len(method_contains)}"
    )

    # 应有 add → log 的 call 边（同文件内方法间调用）
    call_edges = [e for e in graph.edges if e.type == "calls"]
    add_calls = [e for e in call_edges if "add" in e.source]
    assert len(add_calls) >= 1, (
        f"Expected add→log call edge, got {[(e.source, e.target) for e in call_edges]}"
    )

    # 不应该有悬空边（所有 source/target 都应在节点集合中）
    node_ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        assert edge.source in node_ids, (
            f"Dangling edge source: {edge.source} -> {edge.target}"
        )
        assert edge.target in node_ids, (
            f"Dangling edge target: {edge.source} -> {edge.target}"
        )


def test_arrow_function_call_edges_without_validation(tmp_path: Path) -> None:
    """验证箭头函数 caller 会创建稳定节点，validation 关闭时也无悬空边."""
    root = tmp_path / "ts-arrow-calls"
    root.mkdir(parents=True)

    (root / "src").mkdir(parents=True)
    (root / "src" / "app.ts").write_text("""function helper(): void {}

const handler = (): void => {
  helper();
};
""")

    pipeline = Pipeline(root, enable_validation=False, enable_persistence=True)
    result = pipeline.run()

    node_ids = {n.id for n in result.graph.nodes}
    assert "function:src/app.ts:handler" in node_ids
    assert "function:src/app.ts:helper" in node_ids
    assert any(
        e.source == "function:src/app.ts:handler"
        and e.target == "function:src/app.ts:helper"
        and e.type == "calls"
        for e in result.graph.edges
    )
    for edge in result.graph.edges:
        assert edge.source in node_ids, (
            f"Dangling edge source: {edge.source} -> {edge.target}"
        )
        assert edge.target in node_ids, (
            f"Dangling edge target: {edge.source} -> {edge.target}"
        )

    from understand_anything.persistence import load_graph

    reloaded = load_graph(root, validate=False)
    assert reloaded is not None
    reloaded_ids = {n.id for n in reloaded.nodes}
    for edge in reloaded.edges:
        assert edge.source in reloaded_ids
        assert edge.target in reloaded_ids


def test_nested_function_call_edges_without_validation(tmp_path: Path) -> None:
    """验证嵌套函数 caller 会创建稳定节点，validation 关闭时也无悬空边."""
    root = tmp_path / "py-nested-calls"
    root.mkdir(parents=True)

    (root / "main.py").write_text("""def helper() -> None:
    pass


def outer() -> None:
    def inner() -> None:
        helper()
    inner()
""")

    pipeline = Pipeline(root, enable_validation=False, enable_persistence=True)
    result = pipeline.run()

    node_ids = {n.id for n in result.graph.nodes}
    assert "function:main.py:helper" in node_ids
    assert "function:main.py:outer" in node_ids
    assert "function:main.py:inner" in node_ids
    assert any(
        e.source == "function:main.py:inner"
        and e.target == "function:main.py:helper"
        and e.type == "calls"
        for e in result.graph.edges
    )
    for edge in result.graph.edges:
        assert edge.source in node_ids, (
            f"Dangling edge source: {edge.source} -> {edge.target}"
        )
        assert edge.target in node_ids, (
            f"Dangling edge target: {edge.source} -> {edge.target}"
        )

    from understand_anything.persistence import load_graph

    reloaded = load_graph(root, validate=False)
    assert reloaded is not None
    reloaded_ids = {n.id for n in reloaded.nodes}
    for edge in reloaded.edges:
        assert edge.source in reloaded_ids
        assert edge.target in reloaded_ids


# ===========================================================================
# Additional: git hash auto-detection
# ===========================================================================


def test_no_dangling_edges_for_external_calls(tmp_path: Path) -> None:
    """验证外部调用不产生悬空边，且验证清理后的图被正确返回和持久化.

    复现步骤：
    - 创建包含 console.log 调用的 TS 文件
    - 运行管道
    - 确认 result.graph 中不存在指向不存在节点的 call 边
    - 确认持久化的图也不包含悬空边
    """
    root = tmp_path / "ts-external-call"
    root.mkdir(parents=True)

    (root / "src").mkdir(parents=True)
    (root / "src" / "index.ts").write_text("""import { greet } from "./utils";

function main(): void {
  console.log(greet("World"));
  helper();
}

function helper(): void {
  console.log("done");
}

main();
""")
    (root / "src" / "utils.ts").write_text("""export function greet(name: string): string {
  return `Hello, ${name}!`;
}
""")

    pipeline = Pipeline(root, enable_persistence=True)
    result = pipeline.run()

    # 验证不应有悬空边（指向不存在节点的边）
    node_ids = {n.id for n in result.graph.nodes}
    for edge in result.graph.edges:
        assert edge.source in node_ids, (
            f"Dangling source in edge: {edge.source} -> {edge.target}"
        )
        assert edge.target in node_ids, (
            f"Dangling target in edge: {edge.source} -> {edge.target}"
        )

    # console.log 和 greet 不应产生同文件 call 边（它们不在 index.ts 中定义）
    call_edges = [e for e in result.graph.edges if e.type == "calls"]
    for e in call_edges:
        # helper 是 index.ts 中定义的函数，main -> helper 是合法的同文件调用
        assert "main" in e.source or "helper" in e.source
        # greet 是 utils.ts 中的，main 调用它不应成为同文件 call 边
        assert "greet" not in e.target, (
            f"greet should not appear as same-file callee, got {e.target}"
        )
        assert "console.log" not in e.target, (
            f"console.log should not appear as callee, got {e.target}"
        )

    # 验证持久化的图也不包含悬空边
    from understand_anything.persistence import load_graph

    reloaded = load_graph(root)
    assert reloaded is not None
    reloaded_ids = {n.id for n in reloaded.nodes}
    for edge in reloaded.edges:
        assert edge.source in reloaded_ids, (
            f"Persisted dangling source: {edge.source} -> {edge.target}"
        )
        assert edge.target in reloaded_ids, (
            f"Persisted dangling target: {edge.source} -> {edge.target}"
        )


def test_git_hash_auto_detection(mini_python_project: Path) -> None:
    """验证 git hash 自动检测（在 git 仓库内运行时）."""
    pipeline = Pipeline(mini_python_project)
    # 在测试中，项目不在 git 仓库内，所以应该返回 "unknown"
    assert pipeline._git_hash == "unknown"


# ===========================================================================
# Additional: explicit git_hash parameter
# ===========================================================================


def test_explicit_git_hash(mini_python_project: Path) -> None:
    """验证显式传入 git_hash."""
    pipeline = Pipeline(mini_python_project, git_hash="abc123def")
    result = pipeline.run()

    assert result.graph.project.git_commit_hash == "abc123def"
