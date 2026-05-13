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
    # VCS config
    ".gitignore",
    # Node / JS
    "node_modules",
    "vendor/",
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
    # Tool / cache output
    ".understand-anything",
    ".cache/",
    ".turbo/",
    "out/",
    "coverage/",
    "target/",
    "obj/",
    # Lockfiles & large generated files
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.lock",
    # Minified / generated / map files
    "*.min.js",
    "*.map",
    "*.generated.*",
    # License files
    "LICENSE",
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
    """构建合并的 ``pathspec.PathSpec``，从多个忽略文件中读取规则。

    加载顺序（后加载的规则可通过 ``!`` 否定覆盖前面的规则）：

    1. :data:`DEFAULT_IGNORE_PATTERNS` — 内置默认规则
    2. ``.gitignore`` — 项目根目录的 gitignore（当 *include_gitignore* 为
       ``True`` 时；注意这是 Python 端扩展，TypeScript core 不读取
       ``.gitignore``）
    3. ``.understand-anything/.understandignore`` — 工具内部 ignore 文件
    4. ``.understandignore`` — 项目根目录的用户自定义 ignore 文件
       （当 *include_understandignore* 为 ``True`` 时）

    这样项目根 ``.understandignore`` 中的 ``!`` 规则可以覆盖所有前面的规则。

    Args:
        project_root: 项目根目录。
        include_gitignore: 是否读取 ``.gitignore``（默认 ``True``）。
        include_understandignore: 是否读取 ``.understandignore``（默认
            ``True``）。

    Returns:
        合并后的 ``pathspec.PathSpec`` 对象。
    """
    patterns: list[str] = list(DEFAULT_IGNORE_PATTERNS)

    # 2. .gitignore（Python 扩展，TS core 不读取）
    if include_gitignore:
        gi_path = project_root / ".gitignore"
        patterns.extend(_read_ignore_file(gi_path))

    # 3. .understand-anything/.understandignore（工具内部规则）
    ua_ui_path = project_root / ".understand-anything" / ".understandignore"
    patterns.extend(_read_ignore_file(ua_ui_path))

    # 4. 项目根 .understandignore（用户自定义，最后加载以便 ! 覆盖）
    if include_understandignore:
        ui_path = project_root / ".understandignore"
        patterns.extend(_read_ignore_file(ui_path))

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
