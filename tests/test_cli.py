"""CLI 命令测试 — graph build/stats/query 端到端验证."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from understand_anything.cli.cli import cli

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_project_dir(tmp_path: Path) -> Path:
    """创建包含单个子项目的目录, 供 --project-dir 使用."""
    root = tmp_path / "workspace"
    root.mkdir(parents=True)

    proj = root / "myapp"
    proj.mkdir(parents=True)
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.py").write_text(
        '"""Main module."""\n\n'
        "def greet(name: str) -> str:\n"
        '    """Greet someone."""\n'
        '    return f"Hello, {name}"\n\n'
        "def main() -> None:\n"
        '    """Entry point."""\n'
        '    print(greet("World"))\n\n'
        "main()\n"
    )
    return root


# ---------------------------------------------------------------------------
# CLI graph build
# ---------------------------------------------------------------------------


class TestGraphBuild:
    """验证 ``graph build --project-dir <dir>`` 生成图文件."""

    def test_build_creates_graph_json(self, cli_project_dir: Path) -> None:
        """graph build 应该生成 .understand-anything/knowledge-graph.json."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["graph", "build", "--project-dir", str(cli_project_dir)]
        )

        assert result.exit_code == 0, (
            f"CLI failed: {result.output}\n{result.exception}"
        )

        # 验证图文件存在
        graph_file = (
            cli_project_dir
            / "myapp"
            / ".understand-anything"
            / "knowledge-graph.json"
        )
        assert graph_file.is_file(), (
            f"Graph file not found at {graph_file}"
        )

        # 验证文件内容合法
        data = json.loads(graph_file.read_text())
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0, "Graph should have at least one node"

    def test_build_with_sqlite_backend(self, cli_project_dir: Path) -> None:
        """graph build --backend sqlite 应生成 graph.db."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "graph",
                "build",
                "--project-dir",
                str(cli_project_dir),
                "--backend",
                "sqlite",
            ],
        )

        assert result.exit_code == 0, (
            f"CLI failed: {result.output}\n{result.exception}"
        )

        db_file = (
            cli_project_dir
            / "myapp"
            / ".understand-anything"
            / "graph.db"
        )
        assert db_file.is_file(), f"SQLite DB not found at {db_file}"


# ---------------------------------------------------------------------------
# CLI graph stats
# ---------------------------------------------------------------------------


class TestGraphStats:
    """验证 ``graph stats --project-dir <dir>`` 读取项目图."""

    def test_stats_reads_graph(self, cli_project_dir: Path) -> None:
        """先 build 再 stats, 应输出统计信息."""
        runner = CliRunner()

        # 先构建
        build_result = runner.invoke(
            cli, ["graph", "build", "--project-dir", str(cli_project_dir)]
        )
        assert build_result.exit_code == 0

        # 再查看统计
        stats_result = runner.invoke(
            cli, ["graph", "stats", "--project-dir", str(cli_project_dir)]
        )

        assert stats_result.exit_code == 0, (
            f"stats CLI failed: {stats_result.output}"
        )
        # stats 应该输出节点和边数量
        assert "Nodes:" in stats_result.output
        assert "Edges:" in stats_result.output
        assert "myapp" in stats_result.output

    def test_stats_no_graph_shows_message(self, cli_project_dir: Path) -> None:
        """未构建图时 stats 应输出 'no graph found'."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["graph", "stats", "--project-dir", str(cli_project_dir)]
        )

        assert result.exit_code == 0
        assert "no graph found" in result.output
