""".gitignore / .understandignore pattern matching with pathspec.

Python port of ignore-filter.ts.  Uses the ``pathspec`` library (the Python
equivalent of the ``ignore`` npm package) to match file paths against
gitignore-style patterns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pathspec

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Default ignore patterns — always applied unless explicitly overridden
# ---------------------------------------------------------------------------

DEFAULT_IGNORE_PATTERNS: list[str] = [
    # VCS
    ".git",
    ".svn",
    ".hg",
    # Node
    "node_modules",
    # Python
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".venv",
    "venv",
    ".tox",
    "*.egg-info",
    ".eggs",
    "build",
    "dist",
    # IDE
    ".idea",
    ".vscode",
    "*.swp",
    "*.swo",
    "*~",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Tool output
    ".understand-anything",
    # Lockfiles & large generated files
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.lock",
    # Binary / media (too large / not useful for analysis)
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.ico",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp3",
    "*.mp4",
    "*.webm",
    "*.ogg",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.bz2",
    "*.7z",
    "*.rar",
]

# ---------------------------------------------------------------------------
# Specification loading
# ---------------------------------------------------------------------------


def _read_ignore_file(path: Path) -> list[str]:
    """Read an ignore file, returning non-empty, non-comment lines."""
    if not path.is_file():
        return []
    lines: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_ignore_spec(
    project_root: Path,
    *,
    include_gitignore: bool = True,
    include_understandignore: bool = True,
) -> pathspec.PathSpec:
    """Build a combined ``pathspec.PathSpec`` from ignore files.

    Reads ``.gitignore`` and ``.understandignore`` from *project_root*
    (when the corresponding flag is ``True``), merges the patterns with
    :data:`DEFAULT_IGNORE_PATTERNS`, and returns a ready-to-use spec.

    ``.understandignore`` is read **first** so that the project-level
    config can **remove** previously ignored files (gitignore-style
    negation with ``!``).
    """
    patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)

    if include_understandignore:
        ui_path = project_root / ".understandignore"
        patterns.extend(_read_ignore_file(ui_path))

    if include_gitignore:
        gi_path = project_root / ".gitignore"
        patterns.extend(_read_ignore_file(gi_path))

    return pathspec.PathSpec.from_lines("gitignore", patterns)


# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------


def _relative_str(project_root: Path, file_path: Path) -> str:
    """Return *file_path* as a relative POSIX string from *project_root*."""
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        # file_path is outside project_root — use absolute path as-is
        return str(file_path)
    return rel.as_posix()


def should_ignore(
    file_path: Path,
    spec: pathspec.PathSpec,
    *,
    project_root: Path | None = None,
) -> bool:
    """Check whether *file_path* matches any pattern in *spec*.

    If *project_root* is provided, *file_path* is converted to a relative
    POSIX path first; otherwise the absolute path is used.
    """
    target = _relative_str(project_root, file_path) if project_root else str(file_path)
    return spec.match_file(target)


def filter_files(
    file_paths: list[Path],
    spec: pathspec.PathSpec,
    *,
    project_root: Path | None = None,
) -> list[Path]:
    """Return only the paths from *file_paths* that are **not** ignored."""
    return [
        p for p in file_paths if not should_ignore(p, spec, project_root=project_root)
    ]
