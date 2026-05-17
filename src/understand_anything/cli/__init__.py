"""understand-anything CLI 入口."""

from __future__ import annotations

from understand_anything.cli.analyze import analyze
from understand_anything.cli.cli import cli

cli.add_command(analyze)


def main() -> None:
    """CLI 主入口点."""
    cli()
