"""Tests for persistence layer — save/load graph, meta, fingerprints, config."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from understand_anything.types import (
    AnalysisMeta,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    ProjectConfig,
    ProjectMeta,
)
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "test_project"


@pytest.fixture
def sample_graph() -> KnowledgeGraph:
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

    def test_meta_path(self, project_root: Path) -> None:
        assert meta_path(project_root) == output_dir(project_root) / "analysis-meta.json"

    def test_fingerprints_path(self, project_root: Path) -> None:
        assert fingerprints_path(project_root) == output_dir(project_root) / "fingerprints.json"

    def test_config_path(self, project_root: Path) -> None:
        assert config_path(project_root) == output_dir(project_root) / "project-config.json"


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

    def test_serialized_json_is_valid_utf8(self, project_root: Path, sample_graph: KnowledgeGraph) -> None:
        save_graph(project_root, sample_graph)
        raw = graph_path(project_root).read_text()
        data = json.loads(raw)
        assert data["version"] == "1.0.0"


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
        # The file should contain the new hash
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
        # Directory itself survives
        assert output_dir(project_root).is_dir()

    def test_clear_all_missing_dir(self, project_root: Path) -> None:
        # Should not raise
        clear_all(project_root)
