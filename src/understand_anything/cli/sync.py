"""cg sync 命令组 — 增量同步状态和强制同步."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import click

logger = logging.getLogger(__name__)


@click.group(name="sync")
def sync_group() -> None:
    """增量同步管理."""


@sync_group.command(name="status")
@click.option(
    "--project-dir",
    "-p",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="项目根目录.",
)
def sync_status(project_dir: Path) -> None:
    """检查增量同步状态."""
    from understand_anything.persistence import load_meta

    project_root = project_dir.resolve()
    meta = load_meta(project_root)

    if meta is None:
        click.echo(f"No analysis metadata found for: {project_root}")
        return

    click.echo(f"Project: {project_root.name}")
    click.echo(f"  Last analyzed: {meta.last_analyzed_at}")
    click.echo(f"  Git commit:    {meta.git_commit_hash}")
    click.echo(f"  Version:       {meta.version}")
    click.echo(f"  Files:         {meta.analyzed_files}")

    # 使用 staleness 模块检查变更
    from understand_anything.analysis.staleness import is_stale

    stale, changed = is_stale(
        str(project_root), meta.git_commit_hash
    )
    if stale:
        click.echo(f"\n  Status: STALE ({len(changed)} files changed)")
        for f in changed[:10]:
            click.echo(f"    {f}")
        if len(changed) > 10:
            click.echo(f"    ... and {len(changed) - 10} more")
    else:
        click.echo("\n  Status: UP TO DATE")


@sync_group.command(name="force")
@click.option(
    "--project-dir",
    "-p",
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
def sync_force(project_dir: Path, backend: Literal["json", "sqlite"]) -> None:
    """强制执行全量重新同步."""
    from understand_anything.pipeline import Pipeline

    project_root = project_dir.resolve()
    click.echo(f"Force re-syncing: {project_root}")

    pipeline = Pipeline(
        str(project_root),
        backend=backend,
    )
    result = pipeline.run()

    click.echo(
        f"  Done: {result.analyzed_files} files, "
        f"{len(result.graph.nodes)} nodes, "
        f"{len(result.graph.edges)} edges"
    )
