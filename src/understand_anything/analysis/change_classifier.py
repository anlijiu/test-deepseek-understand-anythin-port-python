"""Update decision matrix — classify the type of graph update needed.

Python port of the TypeScript ``change-classifier.ts``.  Analyses structural
changes and decides whether to skip, do a partial update, or trigger a full
re-analysis of architecture and tour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.analysis.fingerprint import ChangeAnalysis


@dataclass
class UpdateDecision:
    """Result of classifying what kind of graph update is needed."""

    action: str  # SKIP | PARTIAL_UPDATE | ARCHITECTURE_UPDATE | FULL_UPDATE
    files_to_reanalyze: list[str] = field(default_factory=list)
    rerun_architecture: bool = False
    rerun_tour: bool = False
    reason: str = ""


def classify_update(
    analysis: ChangeAnalysis,
    total_files_in_graph: int,
    all_known_files: list[str] | None = None,
) -> UpdateDecision:
    """Classify the type of graph update needed from structural change analysis.

    Decision matrix:

    * **SKIP** — all files NONE (no content changes).
    * **PARTIAL_UPDATE** — some STRUCTURAL changes, same directories.
    * **ARCHITECTURE_UPDATE** — new/deleted directories or >10 structural files.
    * **FULL_UPDATE** — >30 structural files or >50% of files changed.
    """
    if all_known_files is None:
        all_known_files = []

    new = analysis.new_files
    deleted = analysis.deleted_files
    structural = analysis.structurally_changed_files
    cosmetic = analysis.cosmetic_only_files

    structural_count = len(structural) + len(new) + len(deleted)

    # No structural changes at all — skip
    if structural_count == 0:
        if cosmetic:
            reason = (
                f"{len(cosmetic)} file(s) have cosmetic-only changes"
                " (no structural impact)"
            )
        else:
            reason = "No changes detected"
        return UpdateDecision(
            action="SKIP",
            rerun_architecture=False,
            rerun_tour=False,
            reason=reason,
        )

    # Too many structural changes — full rebuild
    triggered_by_count = structural_count > 30
    triggered_by_pct = (
        total_files_in_graph > 0
        and structural_count / total_files_in_graph > 0.5
    )
    if triggered_by_count or triggered_by_pct:
        if triggered_by_count and triggered_by_pct:
            threshold = ">30 files and >50% of project"
        elif triggered_by_count:
            threshold = ">30 files"
        else:
            threshold = ">50% of project"
        return UpdateDecision(
            action="FULL_UPDATE",
            files_to_reanalyze=[*structural, *new],
            rerun_architecture=True,
            rerun_tour=True,
            reason=(
                f"{structural_count} files have structural changes"
                f" ({threshold}) — full rebuild recommended"
            ),
        )

    # Check if directory structure changed
    has_dir_changes = _detect_directory_changes(new, deleted, all_known_files)

    if has_dir_changes or structural_count > 10:
        return UpdateDecision(
            action="ARCHITECTURE_UPDATE",
            files_to_reanalyze=[*structural, *new],
            rerun_architecture=True,
            rerun_tour=True,
            reason=(
                f"Directory structure changed ({len(new)} new,"
                f" {len(deleted)} deleted files)"
                if has_dir_changes
                else f"{structural_count} files have structural changes"
                " — architecture re-analysis needed"
            ),
        )

    # Localized structural changes — partial update
    return UpdateDecision(
        action="PARTIAL_UPDATE",
        files_to_reanalyze=[*structural, *new],
        rerun_architecture=False,
        rerun_tour=False,
        reason=(
            f"{structural_count} file(s) have structural changes:"
            f" {_summarize_changes(analysis)}"
        ),
    )


# ===========================================================================
# Internal helpers
# ===========================================================================


def _top_directory(file_path: str) -> str | None:
    """Get the first path segment (top-level directory)."""
    # Normalize to forward slashes for consistency
    normalized = file_path.replace("\\", "/")
    parts = Path(normalized).parts
    if len(parts) <= 1:
        return None
    # Return the first directory component
    for part in parts[:-1]:
        if part and part != ".":
            return part
    return None


def _detect_directory_changes(
    new_files: list[str],
    deleted_files: list[str],
    all_known_files: list[str],
) -> bool:
    """Detect if new/deleted files introduce or remove a top-level directory.

    Compares the set of directories before and after the change to detect
    directories that are added or removed entirely.
    """
    deleted_set = set(deleted_files)

    # Directories that existed before the change
    before_dirs = {
        d for f in all_known_files
        if (d := _top_directory(f)) is not None
    }

    # Directories that exist after the change
    after_dirs: set[str] = set()
    for f in all_known_files:
        if f in deleted_set:
            continue
        d = _top_directory(f)
        if d is not None:
            after_dirs.add(d)
    for f in new_files:
        d = _top_directory(f)
        if d is not None:
            after_dirs.add(d)

    return bool(after_dirs - before_dirs) or bool(before_dirs - after_dirs)


def _summarize_changes(analysis: ChangeAnalysis) -> str:
    """Produce a concise human-readable summary of structural changes."""
    parts: list[str] = []
    if analysis.new_files:
        parts.append(f"{len(analysis.new_files)} new")
    if analysis.deleted_files:
        parts.append(f"{len(analysis.deleted_files)} deleted")
    if analysis.structurally_changed_files:
        parts.append(f"{len(analysis.structurally_changed_files)} modified")
    return ", ".join(parts)
