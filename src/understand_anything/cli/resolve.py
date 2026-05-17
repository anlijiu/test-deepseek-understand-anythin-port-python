"""cg resolve 命令组 — 引用解析."""

from __future__ import annotations

import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group(name="resolve")
def resolve_group() -> None:
    """跨文件引用解析."""


@resolve_group.command(name="references")
@click.argument("file_path")
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="包含多个项目的目录.",
)
@click.option(
    "--language",
    default=None,
    help="语言 ID (e.g. python, typescript).",
)
def resolve_references(
    file_path: str, project_dir: Path, language: str | None
) -> None:
    """解析指定文件中的跨文件引用.

    FILE_PATH: 要分析的文件路径 (相对路径).
    """
    from understand_anything.analysis.resolution import (
        ReferenceResolver,
        build_resolution_context,
    )
    from understand_anything.analysis.resolution.types import (
        UnresolvedRef,
    )
    from understand_anything.persistence import load_graph

    click.echo(f"Resolving references for: {file_path}")

    # 找到包含此文件的项目
    for project in project_dir.iterdir():
        if not project.is_dir() or project.name.startswith("."):
            continue

        full_path = project / file_path
        if not full_path.exists():
            continue

        graph = load_graph(project, validate=False)
        if graph is None:
            click.echo(f"No graph found for project: {project.name}")
            continue

        # 读取文件内容
        try:
            content = full_path.read_text()
        except OSError:
            click.echo(f"Cannot read: {file_path}")
            continue

        # 构建解析上下文
        import_map: dict[str, dict[str, str]] = {}
        export_map: dict[str, set[str]] = {}
        symbol_map: dict[str, list[tuple[str, str]]] = {}
        analyzed_files: set[str] = set()

        for node in graph.nodes:
            if node.file_path:
                analyzed_files.add(node.file_path)
                if node.type.value in (
                    "function",
                    "class",
                    "variable",
                    "enum",
                    "interface",
                ):
                    symbol_map.setdefault(node.name, []).append(
                        (node.file_path, node.type.value)
                    )

        ctx = build_resolution_context(
            workspace_root=str(project),
            analyzed_files=analyzed_files,
            import_map=import_map,
            export_map=export_map,
            symbol_map=symbol_map,
        )

        resolver = ReferenceResolver(ctx)

        # 收集 unresolved refs (简化版)
        import_prefixes = ["import ", "from ", "require(", "#include "]
        unresolved = [
            UnresolvedRef(
                source_file=file_path,
                symbol=line.strip(),
                ref_type="import",
                line_number=line_no,
            )
            for line_no, line in enumerate(content.splitlines(), 1)
            if any(prefix in line for prefix in import_prefixes)
        ]

        if not unresolved:
            click.echo("No unresolved references found.")
            continue

        resolved = resolver.resolve(unresolved, language_id=language)
        click.echo(f"\nUnresolved: {len(unresolved)}")
        click.echo(f"Resolved:   {len(resolved)}")
        for ref in resolved:
            click.echo(
                f"  [{ref.confidence:.0%}] {ref.unresolved.symbol} "
                f"→ {ref.target_file}::{ref.target_symbol} "
                f"({ref.resolution_strategy})"
            )


@resolve_group.command(name="file")
@click.argument("symbol_name")
@click.option(
    "--project-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="包含多个项目的目录.",
)
def resolve_file(symbol_name: str, project_dir: Path) -> None:
    """查找导出指定符号的文件.

    SYMBOL_NAME: 要查找的符号名称.
    """
    from understand_anything.persistence import load_graph

    for project in project_dir.iterdir():
        if not project.is_dir() or project.name.startswith("."):
            continue

        graph = load_graph(project, validate=False)
        if graph is None:
            continue

        matches = [
            node
            for node in graph.nodes
            if node.name == symbol_name
            and node.type.value in ("function", "class", "variable")
        ]

        if matches:
            click.echo(f"\nProject: {project.name}")
            for node in matches:
                click.echo(
                    f"  [{node.type.value}] {node.name} "
                    f"in {node.file_path or 'N/A'} "
                    f"lines {node.line_range or 'N/A'}"
                )
