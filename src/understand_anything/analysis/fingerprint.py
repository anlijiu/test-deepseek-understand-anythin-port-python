"""SHA-256 content hashing + structural fingerprint extraction.

Python port of the TypeScript ``fingerprint.ts``.  Provides structural
fingerprinting for source files to detect meaningful vs cosmetic changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.types import StructuralAnalysis

# ===========================================================================
# Fingerprint data structures
# ===========================================================================


@dataclass
class FileFingerprint:
    """Structural fingerprint of a single source file."""

    @dataclass
    class FuncFingerprint:
        """Function-level fingerprint."""
        name: str
        params: list[str]
        return_type: str | None
        exported: bool
        line_count: int

    @dataclass
    class ClassFingerprint:
        """Class-level fingerprint."""
        name: str
        methods: list[str]
        properties: list[str]
        exported: bool
        line_count: int

    @dataclass
    class ImportFingerprint:
        """Import statement fingerprint."""
        source: str
        specifiers: list[str]

    file_path: str
    content_hash: str
    functions: list[FuncFingerprint] = field(default_factory=list)
    classes: list[ClassFingerprint] = field(default_factory=list)
    imports: list[ImportFingerprint] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    total_lines: int = 0
    has_structural_analysis: bool = False


@dataclass
class FingerprintStore:
    """Collection of file fingerprints for a project snapshot."""
    version: str = "1.0.0"
    git_commit_hash: str = ""
    generated_at: str = ""
    files: dict[str, FileFingerprint] = field(default_factory=dict)


@dataclass
class FileChangeResult:
    """Result of comparing two fingerprints for a single file."""
    file_path: str
    change_level: str  # "NONE" | "STRUCTURAL"
    details: list[str] = field(default_factory=list)


@dataclass
class ChangeAnalysis:
    """Aggregate change analysis across a set of files."""
    file_changes: list[FileChangeResult] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    structurally_changed_files: list[str] = field(default_factory=list)
    cosmetic_only_files: list[str] = field(default_factory=list)
    unchanged_files: list[str] = field(default_factory=list)


# ===========================================================================
# Content hashing
# ===========================================================================


def content_hash(content: str) -> str:
    """Compute SHA-256 hex digest for a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ===========================================================================
# Fingerprint extraction
# ===========================================================================


def extract_file_fingerprint(
    file_path: str,
    content: str,
    analysis: StructuralAnalysis,
) -> FileFingerprint:
    """Extract a structural fingerprint from a file's tree-sitter analysis.

    The fingerprint captures only elements that affect the knowledge graph
    (function/class/import/export signatures), not implementation details.
    """
    h = content_hash(content)
    exported_names = {e.name for e in analysis.exports}

    functions = [
        FileFingerprint.FuncFingerprint(
            name=fn.name,
            params=list(fn.params),
            return_type=fn.return_type,
            exported=fn.name in exported_names,
            line_count=fn.line_range[1] - fn.line_range[0] + 1,
        )
        for fn in analysis.functions
    ]

    classes = [
        FileFingerprint.ClassFingerprint(
            name=cls.name,
            methods=list(cls.methods),
            properties=list(cls.properties),
            exported=cls.name in exported_names,
            line_count=cls.line_range[1] - cls.line_range[0] + 1,
        )
        for cls in analysis.classes
    ]

    imports = [
        FileFingerprint.ImportFingerprint(
            source=imp.source,
            specifiers=list(imp.specifiers),
        )
        for imp in analysis.imports
    ]

    exports_list = [e.name for e in analysis.exports]

    total_lines = len(content.split("\n"))

    return FileFingerprint(
        file_path=file_path,
        content_hash=h,
        functions=functions,
        classes=classes,
        imports=imports,
        exports=exports_list,
        total_lines=total_lines,
        has_structural_analysis=True,
    )


# ===========================================================================
# Fingerprint comparison
# ===========================================================================


def compare_fingerprints(
    old_fp: FileFingerprint,
    new_fp: FileFingerprint,
) -> FileChangeResult:
    """Compare two file fingerprints and determine the change level.

    * ``NONE`` — content hash identical (file unchanged).
    * ``STRUCTURAL`` — content differs: either signatures changed, or body-only
      changes that may affect call graph / summaries.
    """
    details: list[str] = []

    # Fast path: identical content
    if old_fp.content_hash == new_fp.content_hash:
        return FileChangeResult(file_path=new_fp.file_path, change_level="NONE")

    # Conservative path: if either fingerprint lacks structural analysis
    if not old_fp.has_structural_analysis or not new_fp.has_structural_analysis:
        return FileChangeResult(
            file_path=new_fp.file_path,
            change_level="STRUCTURAL",
            details=["no structural analysis available — conservative classification"],
        )

    _compare_functions(old_fp, new_fp, details)
    _compare_classes(old_fp, new_fp, details)
    _compare_imports(old_fp, new_fp, details)
    _compare_exports(old_fp, new_fp, details)

    if details:
        return FileChangeResult(
            file_path=new_fp.file_path,
            change_level="STRUCTURAL",
            details=details,
        )

    # Content changed but signature-level structure is identical.
    # Treat as STRUCTURAL because body-only changes can still affect
    # call-graph edges and LLM-generated summaries — "cosmetic" would be
    # too aggressive and risk a stale graph.
    return FileChangeResult(
        file_path=new_fp.file_path,
        change_level="STRUCTURAL",
        details=["internal logic changed (may affect call graph or summaries)"],
    )


def _compare_functions(
    old_fp: FileFingerprint,
    new_fp: FileFingerprint,
    details: list[str],
) -> None:
    """Compare function signatures between two fingerprints."""
    old_func_names = {f.name for f in old_fp.functions}
    new_func_names = {f.name for f in new_fp.functions}

    details.extend(
        f"new function: {name}" for name in sorted(new_func_names - old_func_names)
    )
    details.extend(
        f"removed function: {name}" for name in sorted(old_func_names - new_func_names)
    )

    for new_fn in new_fp.functions:
        old_fn = next((f for f in old_fp.functions if f.name == new_fn.name), None)
        if old_fn is None:
            continue
        if old_fn.params != new_fn.params:
            details.append(f"params changed: {new_fn.name}")
        if old_fn.return_type != new_fn.return_type:
            details.append(f"return type changed: {new_fn.name}")
        if old_fn.exported != new_fn.exported:
            details.append(f"export status changed: {new_fn.name}")
        if old_fn.line_count > 0:
            ratio = new_fn.line_count / old_fn.line_count
            if ratio > 1.5 or ratio < 0.5:
                details.append(
                    f"significant size change: {new_fn.name}"
                    f" ({old_fn.line_count} -> {new_fn.line_count} lines)"
                )


def _compare_classes(
    old_fp: FileFingerprint,
    new_fp: FileFingerprint,
    details: list[str],
) -> None:
    """Compare class signatures between two fingerprints."""
    old_class_names = {c.name for c in old_fp.classes}
    new_class_names = {c.name for c in new_fp.classes}

    details.extend(
        f"new class: {name}" for name in sorted(new_class_names - old_class_names)
    )
    details.extend(
        f"removed class: {name}" for name in sorted(old_class_names - new_class_names)
    )

    for new_cls in new_fp.classes:
        old_cls = next(
            (c for c in old_fp.classes if c.name == new_cls.name), None
        )
        if old_cls is None:
            continue
        if sorted(old_cls.methods) != sorted(new_cls.methods):
            details.append(f"methods changed: {new_cls.name}")
        if sorted(old_cls.properties) != sorted(new_cls.properties):
            details.append(f"properties changed: {new_cls.name}")
        if old_cls.exported != new_cls.exported:
            details.append(f"export status changed: {new_cls.name}")


def _compare_imports(
    old_fp: FileFingerprint,
    new_fp: FileFingerprint,
    details: list[str],
) -> None:
    """Compare import signatures between two fingerprints."""
    def _import_keys(fp: FileFingerprint) -> str:
        entries = sorted(
            f"{imp.source}:{','.join(sorted(imp.specifiers))}"
            for imp in fp.imports
        )
        return "|".join(entries)

    if _import_keys(old_fp) != _import_keys(new_fp):
        details.append("imports changed")


def _compare_exports(
    old_fp: FileFingerprint,
    new_fp: FileFingerprint,
    details: list[str],
) -> None:
    """Compare export lists between two fingerprints."""
    if sorted(old_fp.exports) != sorted(new_fp.exports):
        details.append("exports changed")
