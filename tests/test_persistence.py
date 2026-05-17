"""Tests for persistence layer — save/load graph, meta, fingerprints, config."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from understand_anything.persistence import (
    clear_all,
    config_path,
    fingerprints_path,
    graph_path,
    load_all,
    load_config,
    load_fingerprints,
    load_graph,
    load_meta,
    meta_path,
    output_dir,
    save_config,
    save_fingerprints,
    save_graph,
    save_meta,
    touch_meta,
)
from understand_anything.types import (
    AnalysisMeta,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    Layer,
    NodeType,
    ProjectConfig,
    ProjectMeta,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "test_project"


@pytest.fixture
def sample_graph(project_root: Path) -> KnowledgeGraph:
    return KnowledgeGraph(
        version="1.0.0",
        kind="codebase",
        project=ProjectMeta(
            name="test",
            languages=["python"],
            frameworks=[],
            description="Test project",
            analyzedAt="2025-01-01T00:00:00Z",
            gitCommitHash="abc123",
        ),
        nodes=[
            GraphNode(
                id="n1",
                name="main",
                type="file",
                summary="Main entry point",
                complexity="moderate",
                filePath="src/main.py",
            ),
        ],
        edges=[
            GraphEdge(
                source="n1",
                target="n1",
                type="contains",
                direction="forward",
                weight=0.5,
            ),
        ],
        layers=[],
        tour=[],
    )


@pytest.fixture
def sample_meta() -> AnalysisMeta:
    return AnalysisMeta(
        lastAnalyzedAt="2025-01-01T00:00:00Z",
        gitCommitHash="abc123",
        version="1.0.0",
        analyzedFiles=42,
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestPathHelpers:
    def test_output_dir(self, project_root: Path) -> None:
        assert output_dir(project_root) == project_root / ".understand-anything"

    def test_graph_path(self, project_root: Path) -> None:
        assert graph_path(project_root) == output_dir(project_root) / "knowledge-graph.json"

    def test_meta_path_uses_contract_name(self, project_root: Path) -> None:
        """P0.2: meta_path returns .understand-anything/meta.json."""
        assert meta_path(project_root) == output_dir(project_root) / "meta.json"

    def test_fingerprints_path(self, project_root: Path) -> None:
        assert fingerprints_path(project_root) == output_dir(project_root) / "fingerprints.json"

    def test_config_path_uses_contract_name(self, project_root: Path) -> None:
        """P0.2: config_path returns .understand-anything/config.json."""
        assert config_path(project_root) == output_dir(project_root) / "config.json"


# ---------------------------------------------------------------------------
# Graph persistence
# ---------------------------------------------------------------------------


class TestSaveLoadGraph:
    def test_save_and_load_roundtrip(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        fp = save_graph(project_root, sample_graph)
        assert fp.is_file()
        loaded = load_graph(project_root)
        assert loaded is not None
        assert loaded.version == sample_graph.version
        assert loaded.project.name == sample_graph.project.name
        assert len(loaded.nodes) == len(sample_graph.nodes)
        assert loaded.nodes[0].id == "n1"

    def test_load_graph_missing_dir(self, project_root: Path) -> None:
        assert load_graph(project_root) is None

    def test_load_graph_corrupt_file(self, project_root: Path) -> None:
        output_dir(project_root).mkdir(parents=True)
        graph_path(project_root).write_text("not json")
        assert load_graph(project_root) is None

    def test_save_graph_creates_dir(self, project_root: Path) -> None:
        save_graph(project_root, KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="x", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[], edges=[], layers=[], tour=[],
        ))
        assert output_dir(project_root).is_dir()

    # -- P0.1: camelCase JSON assertions -----------------------------------

    def test_saved_json_uses_camelcase_keys(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        """P0.1: save_graph writes TS-compatible camelCase field names."""
        save_graph(project_root, sample_graph)
        raw = graph_path(project_root).read_text()
        data = json.loads(raw)

        # Top-level keys remain snake_case (KnowledgeGraph has no aliases).
        assert "version" in data

        # Nested models use camelCase aliases.
        assert "gitCommitHash" in data["project"]
        assert "analyzedAt" in data["project"]

        # Nodes use camelCase.
        assert "filePath" in data["nodes"][0]

        # Snake_case must NOT appear for aliased fields.
        assert "git_commit_hash" not in data["project"]
        assert "analyzed_at" not in data["project"]
        assert "file_path" not in data["nodes"][0]

    def test_saved_json_layers_use_node_ids_alias(self, project_root: Path) -> None:
        """P0.1: Layer.node_ids serialises as nodeIds."""
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[],
            edges=[],
            layers=[Layer(id="L1", name="Core", description="Core layer", nodeIds=["n1", "n2"])],
            tour=[],
        )
        save_graph(project_root, graph)
        data = json.loads(graph_path(project_root).read_text())
        assert "nodeIds" in data["layers"][0]
        assert "node_ids" not in data["layers"][0]

    def test_load_graph_validate_false(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        """P0.4: validate=False still parses JSON into a KnowledgeGraph."""
        save_graph(project_root, sample_graph)
        loaded = load_graph(project_root, validate=False)
        assert loaded is not None
        assert loaded.version == "1.0.0"
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0].id == "n1"

    def test_load_graph_validate_false_corrupt_json(self, project_root: Path) -> None:
        """P0.4: validate=False on corrupt JSON still returns None."""
        output_dir(project_root).mkdir(parents=True)
        graph_path(project_root).write_text("not json")
        assert load_graph(project_root, validate=False) is None

    def test_load_graph_validate_true_uses_schema_pipeline(
        self, project_root: Path
    ) -> None:
        """P0.4: validate=True rejects schema-fatal graphs."""
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[],
            edges=[],
            layers=[],
            tour=[],
        )
        output_dir(project_root).mkdir(parents=True)
        graph_path(project_root).write_text(
            graph.model_dump_json(indent=2, by_alias=True)
        )

        assert load_graph(project_root, validate=True) is None

    def test_load_graph_validate_false_skips_schema_pipeline(
        self, project_root: Path
    ) -> None:
        """P0.4: validate=False skips schema pipeline but keeps Pydantic parsing."""
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[],
            edges=[],
            layers=[],
            tour=[],
        )
        output_dir(project_root).mkdir(parents=True)
        graph_path(project_root).write_text(
            graph.model_dump_json(indent=2, by_alias=True)
        )

        loaded = load_graph(project_root, validate=False)
        assert loaded is not None
        assert loaded.nodes == []

    # -- P0.3: filePath sanitisation ---------------------------------------

    def test_save_graph_sanitises_internal_absolute_path(
        self, project_root: Path
    ) -> None:
        """P0.3: absolute path inside project becomes relative."""
        # project_root is tmp_path/test_project
        project_root.mkdir(parents=True)
        (project_root / "src").mkdir(parents=True)
        (project_root / "src" / "a.py").write_text("")

        abs_path = str(project_root.resolve() / "src" / "a.py")
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[
                GraphNode(
                    id="n1", name="a", type=NodeType.FILE,
                    summary="", complexity="simple", filePath=abs_path,
                ),
            ],
            edges=[], layers=[], tour=[],
        )
        save_graph(project_root, graph)
        data = json.loads(graph_path(project_root).read_text())
        assert data["nodes"][0]["filePath"] == "src/a.py"

    def test_save_graph_sanitises_external_absolute_path(
        self, project_root: Path
    ) -> None:
        """P0.3: absolute path outside project keeps basename only."""
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[
                GraphNode(
                    id="n1", name="gen", type=NodeType.FILE,
                    summary="", complexity="simple",
                    filePath="/tmp/external/generated.py",
                ),
            ],
            edges=[], layers=[], tour=[],
        )
        save_graph(project_root, graph)
        data = json.loads(graph_path(project_root).read_text())
        assert data["nodes"][0]["filePath"] == "generated.py"

    def test_save_graph_keeps_relative_path(self, project_root: Path) -> None:
        """P0.3: already-relative path stays relative."""
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[
                GraphNode(
                    id="n1", name="util", type=NodeType.FILE,
                    summary="", complexity="simple",
                    filePath="src/util.py",
                ),
            ],
            edges=[], layers=[], tour=[],
        )
        save_graph(project_root, graph)
        data = json.loads(graph_path(project_root).read_text())
        assert data["nodes"][0]["filePath"] == "src/util.py"

    def test_save_graph_does_not_mutate_original(
        self, project_root: Path
    ) -> None:
        """P0.3: original KnowledgeGraph object is not modified."""
        project_root.mkdir(parents=True)
        abs_path = str(project_root.resolve() / "src" / "a.py")
        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="t", languages=[], frameworks=[],
                description="", analyzedAt="", gitCommitHash="",
            ),
            nodes=[
                GraphNode(
                    id="n1", name="a", type=NodeType.FILE,
                    summary="", complexity="simple", filePath=abs_path,
                ),
            ],
            edges=[], layers=[], tour=[],
        )
        original_file_path = graph.nodes[0].file_path
        save_graph(project_root, graph)
        # Original must still have the absolute path.
        assert graph.nodes[0].file_path == original_file_path
        assert str(graph.nodes[0].file_path).startswith("/")


# ---------------------------------------------------------------------------
# Meta persistence
# ---------------------------------------------------------------------------


class TestSaveLoadMeta:
    def test_save_load_roundtrip(self, project_root: Path, sample_meta: AnalysisMeta) -> None:
        save_meta(project_root, sample_meta)
        loaded = load_meta(project_root)
        assert loaded is not None
        assert loaded.version == sample_meta.version
        assert loaded.analyzed_files == 42
        assert loaded.git_commit_hash == "abc123"

    def test_load_meta_missing(self, project_root: Path) -> None:
        assert load_meta(project_root) is None

    def test_load_meta_corrupt(self, project_root: Path) -> None:
        output_dir(project_root).mkdir(parents=True)
        meta_path(project_root).write_text("garbage")
        assert load_meta(project_root) is None

    # -- P0.1: camelCase JSON assertions -----------------------------------

    def test_saved_meta_json_uses_camelcase_keys(
        self, project_root: Path, sample_meta: AnalysisMeta
    ) -> None:
        """P0.1: save_meta writes camelCase (e.g. lastAnalyzedAt)."""
        save_meta(project_root, sample_meta)
        data = json.loads(meta_path(project_root).read_text())
        assert "lastAnalyzedAt" in data
        assert "gitCommitHash" in data
        assert "analyzedFiles" in data
        assert "last_analyzed_at" not in data
        assert "git_commit_hash" not in data
        assert "analyzed_files" not in data

    # -- P0.2: legacy filename fallback ------------------------------------

    def test_load_meta_falls_back_to_legacy_filename(
        self, project_root: Path, sample_meta: AnalysisMeta
    ) -> None:
        """P0.2: load_meta reads legacy analysis-meta.json if meta.json missing."""
        out = output_dir(project_root)
        out.mkdir(parents=True)
        # Write to old filename using camelCase (simulating a prior run).
        legacy_path = out / "analysis-meta.json"
        legacy_path.write_text(sample_meta.model_dump_json(indent=2, by_alias=True))
        # Verify new filename does NOT exist.
        assert not (out / "meta.json").is_file()

        loaded = load_meta(project_root)
        assert loaded is not None
        assert loaded.version == "1.0.0"
        assert loaded.analyzed_files == 42


class TestTouchMeta:
    def test_creates_new_meta(self, project_root: Path) -> None:
        meta = touch_meta(project_root, git_commit_hash="def456", version="2.0.0")
        assert meta.git_commit_hash == "def456"
        assert meta.version == "2.0.0"
        assert meta.analyzed_files == 0

    def test_overwrites_existing_meta(self, project_root: Path, sample_meta: AnalysisMeta) -> None:
        save_meta(project_root, sample_meta)
        meta = touch_meta(project_root, git_commit_hash="xyz", analyzed_files=99)
        assert meta.git_commit_hash == "xyz"
        assert meta.analyzed_files == 99
        loaded = load_meta(project_root)
        assert loaded is not None
        assert loaded.git_commit_hash == "xyz"


# ---------------------------------------------------------------------------
# Fingerprints persistence
# ---------------------------------------------------------------------------


class TestFingerprints:
    def test_save_load_roundtrip(self, project_root: Path) -> None:
        fps = {"src/main.py": "abc123", "src/utils.py": "def456"}
        save_fingerprints(project_root, fps)
        loaded = load_fingerprints(project_root)
        assert loaded == fps

    def test_load_missing(self, project_root: Path) -> None:
        assert load_fingerprints(project_root) == {}

    def test_load_corrupt(self, project_root: Path) -> None:
        output_dir(project_root).mkdir(parents=True)
        fingerprints_path(project_root).write_text("not valid json")
        assert load_fingerprints(project_root) == {}

    def test_load_non_dict_json(self, project_root: Path) -> None:
        output_dir(project_root).mkdir(parents=True)
        fingerprints_path(project_root).write_text("[1, 2, 3]")
        assert load_fingerprints(project_root) == {}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


class TestConfig:
    def test_save_load_roundtrip(self, project_root: Path) -> None:
        cfg = ProjectConfig(autoUpdate=True)
        save_config(project_root, cfg)
        loaded = load_config(project_root)
        assert loaded.auto_update is True

    def test_load_missing_returns_default(self, project_root: Path) -> None:
        loaded = load_config(project_root)
        assert loaded.auto_update is False

    def test_load_corrupt_returns_default(self, project_root: Path) -> None:
        output_dir(project_root).mkdir(parents=True)
        config_path(project_root).write_text("broken")
        loaded = load_config(project_root)
        assert loaded.auto_update is False

    # -- P0.1: camelCase JSON assertions -----------------------------------

    def test_saved_config_json_uses_auto_update_alias(
        self, project_root: Path
    ) -> None:
        """P0.1: save_config writes autoUpdate in raw JSON."""
        cfg = ProjectConfig(autoUpdate=True)
        save_config(project_root, cfg)
        data = json.loads(config_path(project_root).read_text())
        assert "autoUpdate" in data
        assert "auto_update" not in data

    # -- P0.2: legacy filename fallback ------------------------------------

    def test_load_config_falls_back_to_legacy_filename(
        self, project_root: Path
    ) -> None:
        """P0.2: load_config reads legacy project-config.json if config.json missing."""
        out = output_dir(project_root)
        out.mkdir(parents=True)
        cfg = ProjectConfig(autoUpdate=True)
        legacy_path = out / "project-config.json"
        legacy_path.write_text(cfg.model_dump_json(indent=2, by_alias=True))
        # Verify new filename does NOT exist.
        assert not (out / "config.json").is_file()

        loaded = load_config(project_root)
        assert loaded.auto_update is True


# ---------------------------------------------------------------------------
# Bulk helpers
# ---------------------------------------------------------------------------


class TestLoadAll:
    def test_all_missing(self, project_root: Path) -> None:
        result = load_all(project_root)
        assert result["graph"] is None
        assert result["meta"] is None
        assert result["fingerprints"] == {}
        assert result["config"].auto_update is False

    def test_all_present(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        save_graph(project_root, sample_graph)
        save_fingerprints(project_root, {"a": "b"})
        save_config(project_root, ProjectConfig(autoUpdate=True))
        touch_meta(project_root, git_commit_hash="abc")

        result = load_all(project_root)
        assert result["graph"] is not None
        assert result["meta"] is not None
        assert result["fingerprints"] == {"a": "b"}
        assert result["config"].auto_update is True


class TestClearAll:
    def test_clear_all_removes_files(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        save_graph(project_root, sample_graph)
        save_fingerprints(project_root, {"a": "b"})
        assert graph_path(project_root).is_file()
        assert fingerprints_path(project_root).is_file()

        clear_all(project_root)
        assert not graph_path(project_root).is_file()
        assert not fingerprints_path(project_root).is_file()
        assert output_dir(project_root).is_dir()

    def test_clear_all_missing_dir(self, project_root: Path) -> None:
        # Should not raise
        clear_all(project_root)


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------


class TestSqliteBackend:
    """验证 ``SqliteBackend.save_graph`` 正确处理各类图数据."""

    def test_save_interface_extends_no_dangling_edges(
        self, tmp_path: Path
    ) -> None:
        """接口 extends 边不应产生 dangling edge (跨文件解析后目标节点存在)."""
        from understand_anything.persistence.sqlite_backend import (
            SqliteBackend,
        )

        root = tmp_path / "test_iface_extends"
        root.mkdir(parents=True)

        # 构建图: 两个文件, 各有一个接口, 其中一个 extends 另一个
        # file_a.ts: interface Base { ... }
        # file_b.ts: interface Child extends Base { ... }
        nodes = [
            GraphNode(
                id="file:src/a.ts",
                name="a.ts",
                type="file",
                filePath="src/a.ts",
                summary="File A",
                complexity="simple",
            ),
            GraphNode(
                id="interface:src/a.ts:Base",
                name="Base",
                type="interface",
                filePath="src/a.ts",
                summary="Base interface",
                complexity="simple",
            ),
            GraphNode(
                id="file:src/b.ts",
                name="b.ts",
                type="file",
                filePath="src/b.ts",
                summary="File B",
                complexity="simple",
            ),
            GraphNode(
                id="interface:src/b.ts:Child",
                name="Child",
                type="interface",
                filePath="src/b.ts",
                summary="Child interface",
                complexity="simple",
            ),
        ]
        edges = [
            GraphEdge(
                source="file:src/a.ts",
                target="interface:src/a.ts:Base",
                type="contains",
                direction="forward",
                weight=1.0,
            ),
            GraphEdge(
                source="file:src/b.ts",
                target="interface:src/b.ts:Child",
                type="contains",
                direction="forward",
                weight=1.0,
            ),
            # Child extends Base — 目标节点 interface:src/a.ts:Base 存在
            GraphEdge(
                source="interface:src/b.ts:Child",
                target="interface:src/a.ts:Base",
                type="inherits",
                direction="forward",
                weight=0.9,
            ),
        ]

        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="test-iface-extends",
                languages=["typescript"],
                frameworks=[],
                description="",
                analyzedAt="2025-01-01T00:00:00Z",
                gitCommitHash="abc",
            ),
            nodes=nodes,
            edges=edges,
            layers=[],
            tour=[],
        )

        backend = SqliteBackend(root)
        try:
            count = backend.save_graph(graph)
            # 应该写入 4 个节点
            assert count == 4
            # 验证数据可读
            assert backend.queries.count_nodes() == 4
            assert backend.queries.count_edges() == 3
        finally:
            backend.close()

    def test_unresolved_extends_no_dangling_edge(
        self, tmp_path: Path
    ) -> None:
        """未解析的 extends 不应产生 dangling edge (目标节点不存在时跳过)."""
        from understand_anything.persistence.sqlite_backend import (
            SqliteBackend,
        )

        root = tmp_path / "test_unresolved_extends"
        root.mkdir(parents=True)

        # 只有 Child 接口, Base 在同一文件且不存在节点
        # 模拟 resolve_inheritance_edges 已跳过未解析边的结果
        nodes = [
            GraphNode(
                id="file:src/b.ts",
                name="b.ts",
                type="file",
                filePath="src/b.ts",
                summary="File B",
                complexity="simple",
            ),
            GraphNode(
                id="interface:src/b.ts:Child",
                name="Child",
                type="interface",
                filePath="src/b.ts",
                summary="Child interface",
                complexity="simple",
            ),
        ]
        edges = [
            GraphEdge(
                source="file:src/b.ts",
                target="interface:src/b.ts:Child",
                type="contains",
                direction="forward",
                weight=1.0,
            ),
            # 没有 extends 边, 因为 Base 不存在于任何已分析文件中
        ]

        graph = KnowledgeGraph(
            version="1.0.0",
            project=ProjectMeta(
                name="test-unresolved",
                languages=["typescript"],
                frameworks=[],
                description="",
                analyzedAt="2025-01-01T00:00:00Z",
                gitCommitHash="abc",
            ),
            nodes=nodes,
            edges=edges,
            layers=[],
            tour=[],
        )

        backend = SqliteBackend(root)
        try:
            count = backend.save_graph(graph)
            assert count == 2
            assert backend.queries.count_edges() == 1
            # 确认没有 inherits 边
            inherits_edges = backend.queries.get_edges_by_type("inherits")
            assert len(inherits_edges) == 0
        finally:
            backend.close()
