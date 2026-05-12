"""Tests for analysis/change_classifier.py — port of change-classifier.test.ts."""

from __future__ import annotations

from understand_anything.analysis.change_classifier import classify_update
from understand_anything.analysis.fingerprint import ChangeAnalysis, FileChangeResult


def _make_analysis(**overrides) -> ChangeAnalysis:
    defaults: dict = {
        "file_changes": [],
        "new_files": [],
        "deleted_files": [],
        "structurally_changed_files": [],
        "cosmetic_only_files": [],
        "unchanged_files": [],
    }
    return ChangeAnalysis(**{**defaults, **overrides})


def _make_change(file_path: str, level: str, details: list[str] | None = None) -> FileChangeResult:
    return FileChangeResult(
        file_path=file_path,
        change_level=level,
        details=details or [],
    )


class TestClassifyUpdate:
    """Port of describe('classifyUpdate', ...)."""

    def test_returns_skip_when_no_structural_changes(self) -> None:
        analysis = _make_analysis(
            cosmetic_only_files=["src/a.ts"],
            file_changes=[
                _make_change("src/a.ts", "COSMETIC", ["internal logic changed"]),
            ],
        )
        decision = classify_update(analysis, 100)
        assert decision.action == "SKIP"
        assert not decision.rerun_architecture
        assert not decision.rerun_tour
        assert decision.files_to_reanalyze == []

    def test_returns_skip_when_no_changes_at_all(self) -> None:
        analysis = _make_analysis()
        decision = classify_update(analysis, 100)
        assert decision.action == "SKIP"
        assert "No changes detected" in decision.reason

    def test_returns_partial_update_for_localized_structural_changes(
        self,
    ) -> None:
        analysis = _make_analysis(
            structurally_changed_files=["src/a.ts", "src/b.ts"],
            file_changes=[
                _make_change("src/a.ts", "STRUCTURAL", ["params changed: foo"]),
                _make_change("src/b.ts", "STRUCTURAL", ["new function: bar"]),
            ],
        )
        decision = classify_update(analysis, 100, ["src/a.ts", "src/b.ts", "src/c.ts"])
        assert decision.action == "PARTIAL_UPDATE"
        assert decision.files_to_reanalyze == ["src/a.ts", "src/b.ts"]
        assert not decision.rerun_architecture
        assert not decision.rerun_tour

    def test_returns_architecture_update_for_more_than_10_structural_files(
        self,
    ) -> None:
        changed = [f"src/file{i}.ts" for i in range(15)]
        analysis = _make_analysis(
            structurally_changed_files=changed,
            file_changes=[
                _make_change(f, "STRUCTURAL", ["modified"]) for f in changed
            ],
        )
        decision = classify_update(analysis, 100)
        assert decision.action == "ARCHITECTURE_UPDATE"
        assert decision.rerun_architecture
        assert decision.rerun_tour

    def test_returns_full_update_for_more_than_30_structural_files(self) -> None:
        changed = [f"src/file{i}.ts" for i in range(35)]
        analysis = _make_analysis(
            structurally_changed_files=changed,
            file_changes=[
                _make_change(f, "STRUCTURAL", ["modified"]) for f in changed
            ],
        )
        decision = classify_update(analysis, 100)
        assert decision.action == "FULL_UPDATE"
        assert decision.rerun_architecture
        assert decision.rerun_tour

    def test_returns_full_update_for_more_than_50_percent_change(self) -> None:
        changed = [f"src/file{i}.ts" for i in range(6)]
        analysis = _make_analysis(
            structurally_changed_files=changed,
            file_changes=[
                _make_change(f, "STRUCTURAL", ["modified"]) for f in changed
            ],
        )
        # 6 of 10 files = 60%
        decision = classify_update(analysis, 10)
        assert decision.action == "FULL_UPDATE"

    def test_includes_new_files_in_reanalysis_list(self) -> None:
        analysis = _make_analysis(
            structurally_changed_files=["src/a.ts"],
            new_files=["src/new.ts"],
            file_changes=[
                _make_change("src/a.ts", "STRUCTURAL", ["modified"]),
                _make_change("src/new.ts", "STRUCTURAL", ["new file"]),
            ],
        )
        decision = classify_update(analysis, 100, ["src/a.ts", "src/b.ts"])
        assert "src/a.ts" in decision.files_to_reanalyze
        assert "src/new.ts" in decision.files_to_reanalyze

    def test_detects_directory_structure_changes(self) -> None:
        analysis = _make_analysis(
            new_files=["new-feature/a.ts"],
            deleted_files=["old-feature/b.ts"],
            structurally_changed_files=["src/a.ts"],
            file_changes=[
                _make_change("new-feature/a.ts", "STRUCTURAL", ["new file"]),
                _make_change("old-feature/b.ts", "STRUCTURAL", ["file deleted"]),
                _make_change("src/a.ts", "STRUCTURAL", ["modified"]),
            ],
        )
        decision = classify_update(
            analysis, 100, ["src/a.ts", "src/b.ts"]
        )
        assert decision.action == "ARCHITECTURE_UPDATE"
        assert decision.rerun_architecture
        assert decision.rerun_tour

    def test_detects_deleted_directory_when_file_in_all_known(self) -> None:
        """Regression: all_known_files includes the deleted file (real input shape).

        When the last file in a directory is deleted, the directory itself
        disappears.  classify_update() must detect this as an architecture
        change even when the deleted file is listed in all_known_files.
        """
        analysis = _make_analysis(
            deleted_files=["old-feature/b.ts"],
            structurally_changed_files=["old-feature/b.ts"],
            file_changes=[
                _make_change("old-feature/b.ts", "STRUCTURAL", ["file deleted"]),
            ],
        )
        decision = classify_update(
            analysis,
            100,
            # Real input: the deleted file WAS in the set of known files
            all_known_files=["old-feature/b.ts", "src/a.ts"],
        )
        assert decision.action == "ARCHITECTURE_UPDATE", (
            f"Expected ARCHITECTURE_UPDATE but got {decision.action}:"
            f" {decision.reason}"
        )
        assert decision.rerun_architecture
        assert decision.rerun_tour
