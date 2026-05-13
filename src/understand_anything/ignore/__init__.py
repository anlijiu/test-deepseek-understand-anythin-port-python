"""Ignore filtering — pathspec-based file exclusion.

Re-exports the main public API from the submodules.
"""

from __future__ import annotations

from understand_anything.ignore.filter import (
    DEFAULT_IGNORE_PATTERNS,
    filter_files,
    load_ignore_spec,
    should_ignore,
)
from understand_anything.ignore.generator import (
    generate_starter_ignore_file,
    generate_understandignore,
    guess_ignore_rules,
)

__all__ = [
    "DEFAULT_IGNORE_PATTERNS",
    "filter_files",
    "generate_starter_ignore_file",
    "generate_understandignore",
    "guess_ignore_rules",
    "load_ignore_spec",
    "should_ignore",
]
