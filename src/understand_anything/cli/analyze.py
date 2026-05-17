"""analyze 命令 — 对指定项目执行知识图谱分析."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

import click

from understand_anything.pipeline import Pipeline

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_NO_PROJECTS_DIRS_MSG = "请通过 --project-dir 指定至少一个项目根目录."


@click.command()
@click.pass_context
def analyze(ctx: click.Context) -> None:
    """对 --project-dir 指定的项目执行完整分析管道."""
    project_dirs: list[Path] = ctx.obj.get("project_dirs", [])

    if not project_dirs:
        raise click.UsageError(_NO_PROJECTS_DIRS_MSG)

    success_count = 0
    fail_count = 0

    for project_root in project_dirs:
        click.echo(f"正在分析: {project_root}")
        try:
            pipeline = Pipeline(project_root)
            result = pipeline.run()
            click.echo(
                f"  完成: {result.analyzed_files} 个文件已分析, "
                f"{result.ignored_files} 个文件已忽略, "
                f"{len(result.graph.nodes)} 个节点, "
                f"{len(result.graph.edges)} 条边."
            )
            success_count += 1
        except Exception:
            click.echo(f"  失败: {project_root}", err=True)
            traceback.print_exc()
            fail_count += 1

    click.echo(f"\n总计: {success_count} 成功, {fail_count} 失败")
