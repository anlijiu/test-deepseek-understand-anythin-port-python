"""cg graph 命令组 — 图构建、查询和统计."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import click

logger = logging.getLogger(__name__)


@click.group(name="graph")
def graph_group() -> None:
    """知识图谱的构建、查询和统计."""


@graph_group.command(name="build")
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="项目根目录.",
)
@click.option(
    "--backend",
    type=click.Choice(["json", "sqlite"]),
    default="json",
    help="持久化后端 (默认: json).",
)
def build_graph(
    project_dir: Path, backend: Literal["json", "sqlite"]
) -> None:
    """构建知识图谱.

    扫描项目目录中的所有文件, 分析代码结构, 构建知识图谱并持久化.
    """
    from understand_anything.pipeline import Pipeline

    for project in project_dir.iterdir():
        if not project.is_dir() or project.name.startswith("."):
            continue

        click.echo(f"Building graph for: {project.name}")
        pipeline = Pipeline(
            str(project),
            backend=backend,
        )
        result = pipeline.run()
        click.echo(
            f"  Nodes: {len(result.graph.nodes)}, "
            f"Edges: {len(result.graph.edges)}, "
            f"Files: {result.analyzed_files}"
        )


@graph_group.command(name="query")
@click.argument("node_name")
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="项目根目录.",
)
def query_graph(node_name: str, project_dir: Path) -> None:
    """按名称查询节点.

    NODE_NAME: 要查找的节点名称.
    """
    from understand_anything.persistence import load_graph

    for project in project_dir.iterdir():
        if not project.is_dir() or project.name.startswith("."):
            continue

        graph = load_graph(project, validate=False)
        if graph is None:
            continue

        matches = [
            node for node in graph.nodes if node_name.lower() in node.name.lower()
        ]
        if matches:
            click.echo(f"\nProject: {project.name}")
            for node in matches[:20]:
                click.echo(
                    f"  [{node.type.value}] {node.name} "
                    f"({node.file_path or 'N/A'})"
                )


@graph_group.command(name="stats")
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="项目根目录.",
)
def graph_stats(project_dir: Path) -> None:
    """显示图统计信息."""
    from understand_anything.persistence import load_graph

    for project in project_dir.iterdir():
        if not project.is_dir() or project.name.startswith("."):
            continue

        graph = load_graph(project, validate=False)
        if graph is None:
            click.echo(f"{project.name}: no graph found")
            continue

        type_counts: dict[str, int] = {}
        for node in graph.nodes:
            t = node.type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        edge_counts: dict[str, int] = {}
        for edge in graph.edges:
            t = edge.type.value
            edge_counts[t] = edge_counts.get(t, 0) + 1

        click.echo(f"\nProject: {project.name}")
        click.echo(f"  Languages: {graph.project.languages}")
        click.echo(f"  Frameworks: {graph.project.frameworks}")
        click.echo(f"  Nodes: {len(graph.nodes)}")
        for t, count in sorted(type_counts.items()):
            click.echo(f"    {t}: {count}")
        click.echo(f"  Edges: {len(graph.edges)}")
        for t, count in sorted(edge_counts.items()):
            click.echo(f"    {t}: {count}")
