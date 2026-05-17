"""顶层 Click group 定义."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from understand_anything.cli.graph import graph_group
from understand_anything.cli.resolve import resolve_group
from understand_anything.cli.sync import sync_group
from understand_anything.cli.watch import watch_command

logger = logging.getLogger(__name__)


@click.group(
    invoke_without_command=True,
)
@click.option(
    "--project-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        resolve_path=True,
        path_type=Path,
    ),
    multiple=True,
    help="要分析的项目的根目录（绝对路径），可多次指定.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    project_dir: tuple[Path, ...],
) -> None:
    """understand-anything — 知识图谱构建工具.

    分析项目代码库并生成知识图谱.

    当指定 --project-dir 且无子命令时，默认执行 analyze.
    """
    ctx.ensure_object(dict)
    ctx.obj["project_dirs"] = list(project_dir) if project_dir else []

    # 无子命令但提供了 --project-dir: 默认执行 analyze
    if ctx.invoked_subcommand is None and project_dir:
        from understand_anything.cli.analyze import analyze

        ctx.invoke(analyze)


# 注册子命令组
cli.add_command(graph_group)
cli.add_command(resolve_group)
cli.add_command(watch_command)
cli.add_command(sync_group)
