"""cg watch 命令 — 文件监听和增量同步."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import click

logger = logging.getLogger(__name__)


@click.command(name="watch")
@click.option(
    "--project",
    "-p",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="项目根目录.",
)
@click.option(
    "--debounce",
    default=2.0,
    type=float,
    help="防抖延迟秒数 (默认: 2.0).",
)
@click.option(
    "--backend",
    type=click.Choice(["json", "sqlite"]),
    default="json",
    help="持久化后端 (默认: json).",
)
def watch_command(
    project: Path, debounce: float, backend: Literal["json", "sqlite"]
) -> None:
    """监听文件变更并自动增量重新索引.

    持续监控项目目录中的文件变更, 在检测到变更后触发增量重新分析.
    """
    from understand_anything.persistence import create_backend
    from understand_anything.pipeline import Pipeline
    from understand_anything.sync import IncrementalSyncer

    project_root = project.resolve()

    click.echo(f"Watching project: {project_root}")
    click.echo("Press Ctrl+C to stop.\n")

    # 初始化同步器
    pipeline = Pipeline(
        str(project_root),
        backend=backend,
    )
    _, sqlite = create_backend(str(project_root), backend=backend)
    syncer = IncrementalSyncer(pipeline, sqlite)
    syncer.load_fingerprints()

    # 首次全量分析
    click.echo("Running initial analysis...")
    stats = syncer.sync_all()
    click.echo(
        f"  Analyzed: {stats['analyzed']} files, "
        f"Nodes: {stats['nodes']}, Edges: {stats['edges']}"
    )

    # 定义变更回调
    def on_change(
        added: set[str], modified: set[str], deleted: set[str]
    ) -> None:
        click.echo(
            f"\nChange detected: +{len(added)} ~{len(modified)} -{len(deleted)}"
        )
        stats = syncer.sync_files(added, modified, deleted)
        click.echo(
            f"  Re-analyzed: Nodes: {stats.get('nodes', 0)}, "
            f"Edges: {stats.get('edges', 0)}"
        )

    # 启动文件监听
    try:
        from understand_anything.sync.watcher import FileWatcher

        watcher = FileWatcher(
            str(project_root),
            on_change=on_change,
            debounce_seconds=debounce,
        )
        watcher.start()

        # 保持运行
        import time

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            click.echo("\nStopping watcher...")
        finally:
            watcher.stop()
            if sqlite:
                sqlite.close()

    except ImportError:
        click.echo(
            "Error: watchdog is required for file watching.\n"
            "Install it with: pip install watchdog"
        )
