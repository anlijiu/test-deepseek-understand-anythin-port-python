"""Tests for analysis/fingerprint.py — port of fingerprint.test.ts."""

from __future__ import annotations

from understand_anything.analysis.fingerprint import (
    FileFingerprint,
    compare_fingerprints,
    content_hash,
    extract_file_fingerprint,
)
from understand_anything.types import (
    ClassInfo,
    FunctionInfo,
    MethodInfo,
    StructuralAnalysis,
)


def _make_analysis(
    *,
    functions: list | None = None,
    classes: list | None = None,
    imports: list | None = None,
    exports: list | None = None,
) -> StructuralAnalysis:
    return StructuralAnalysis(
        functions=functions or [],
        classes=classes or [],
        imports=imports or [],
        exports=exports or [],
    )


class TestContentHash:
    """Port of describe('contentHash', ...)."""

    def test_produces_consistent_sha256_hash(self) -> None:
        assert content_hash("hello world") == content_hash("hello world")

    def test_different_content_produces_different_hash(self) -> None:
        assert content_hash("hello") != content_hash("world")

    def test_hash_is_hex_string(self) -> None:
        h = content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestExtractFileFingerprint:
    """Port of describe('extractFileFingerprint', ...)."""

    def test_extracts_function_signatures(self) -> None:
        analysis = _make_analysis(
            functions=[
                FunctionInfo(name="processData", line_range=(10, 25), params=["input"], return_type="string"),
                FunctionInfo(name="validate", line_range=(30, 40), params=["data"]),
            ],
        )
        fp = extract_file_fingerprint("src/utils.ts", "line1\nline2\nline3", analysis)
        assert len(fp.functions) == 2
        assert fp.functions[0].name == "processData"
        assert fp.functions[0].params == ["input"]
        assert fp.functions[0].return_type == "string"
        assert fp.functions[0].line_count == 16  # 25-10+1

    def test_extracts_class_signatures(self) -> None:
        analysis = _make_analysis(
            classes=[
                ClassInfo(name="DataStore", line_range=(50, 100), methods=["get", "set"], method_details=[MethodInfo(name="get", line_range=(0, 0)), MethodInfo(name="set", line_range=(0, 0))], properties=["data"]),
            ],
        )
        fp = extract_file_fingerprint("src/store.ts", "line\n" * 10, analysis)
        assert len(fp.classes) == 1
        assert fp.classes[0].name == "DataStore"
        assert fp.classes[0].methods == ["get", "set"]
        assert fp.classes[0].properties == ["data"]
        assert fp.classes[0].line_count == 51  # 100-50+1

    def test_computes_total_lines_from_content(self) -> None:
        content = "line1\nline2\nline3\n"
        analysis = _make_analysis()
        fp = extract_file_fingerprint("a.ts", content, analysis)
        assert fp.total_lines == 4  # split('\n') on trailing newline = 4

    def test_marks_has_structural_analysis_true(self) -> None:
        fp = extract_file_fingerprint("a.ts", "content", _make_analysis())
        assert fp.has_structural_analysis is True


class TestCompareFingerprints:
    """Port of describe('compareFingerprints', ...)."""

    def _fp(self, **overrides) -> FileFingerprint:
        defaults: dict = {
            "file_path": "src/app.ts",
            "content_hash": "abc123",
            "functions": [],
            "classes": [],
            "imports": [],
            "exports": [],
            "total_lines": 100,
            "has_structural_analysis": True,
        }
        return FileFingerprint(**{**defaults, **overrides})

    def test_detects_none_when_content_hashes_match(self) -> None:
        fp = self._fp(content_hash="samehash")
        result = compare_fingerprints(fp, fp)
        assert result.change_level == "NONE"
        assert result.details == []

    def test_detects_structural_when_content_differs_but_signatures_same(
        self,
    ) -> None:
        """Body-only changes are STRUCTURAL, not cosmetic — they may affect
        call graph edges and LLM summaries even when signatures match."""
        old_fp = self._fp(
            content_hash="oldhash",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type=None, exported=False, line_count=5)],
        )
        new_fp = self._fp(
            content_hash="newhash",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type=None, exported=False, line_count=5)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"

    def test_detects_structural_when_function_added(self) -> None:
        old_fp = self._fp(content_hash="old")
        new_fp = self._fp(
            content_hash="new",
            functions=[FileFingerprint.FuncFingerprint(name="newFunc", params=[], return_type=None, exported=False, line_count=3)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("new function" in d for d in result.details)

    def test_detects_structural_when_function_removed(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            functions=[FileFingerprint.FuncFingerprint(name="oldFunc", params=[], return_type=None, exported=False, line_count=3)],
        )
        new_fp = self._fp(content_hash="new")
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("removed function" in d for d in result.details)

    def test_detects_structural_when_params_changed(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=["a"], return_type=None, exported=False, line_count=5)],
        )
        new_fp = self._fp(
            content_hash="new",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=["a", "b"], return_type=None, exported=False, line_count=5)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("params changed" in d for d in result.details)

    def test_detects_structural_when_return_type_changed(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type="int", exported=False, line_count=5)],
        )
        new_fp = self._fp(
            content_hash="new",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type="string", exported=False, line_count=5)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("return type changed" in d for d in result.details)

    def test_detects_structural_when_export_status_changes(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type=None, exported=False, line_count=5)],
        )
        new_fp = self._fp(
            content_hash="new",
            functions=[FileFingerprint.FuncFingerprint(name="foo", params=[], return_type=None, exported=True, line_count=5)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"

    def test_detects_structural_when_class_methods_change(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            classes=[FileFingerprint.ClassFingerprint(name="Foo", methods=["get"], properties=[], exported=False, line_count=10)],
        )
        new_fp = self._fp(
            content_hash="new",
            classes=[FileFingerprint.ClassFingerprint(name="Foo", methods=["get", "set"], properties=[], exported=False, line_count=10)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("methods changed" in d for d in result.details)

    def test_detects_structural_when_class_properties_change(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            classes=[FileFingerprint.ClassFingerprint(name="Foo", methods=[], properties=["a"], exported=False, line_count=10)],
        )
        new_fp = self._fp(
            content_hash="new",
            classes=[FileFingerprint.ClassFingerprint(name="Foo", methods=[], properties=["a", "b"], exported=False, line_count=10)],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
        assert any("properties changed" in d for d in result.details)

    def test_detects_structural_when_imports_change(self) -> None:
        old_fp = self._fp(
            content_hash="old",
            imports=[FileFingerprint.ImportFingerprint(source="lodash", specifiers=["map"])],
        )
        new_fp = self._fp(
            content_hash="new",
            imports=[FileFingerprint.ImportFingerprint(source="lodash", specifiers=["map", "filter"])],
        )
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"

    def test_detects_structural_when_exports_change(self) -> None:
        old_fp = self._fp(content_hash="old", exports=["foo"])
        new_fp = self._fp(content_hash="new", exports=["foo", "bar"])
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"

    def test_is_conservative_when_has_structural_analysis_false(self) -> None:
        old_fp = self._fp(content_hash="old")
        new_fp = self._fp(content_hash="new", has_structural_analysis=False)
        result = compare_fingerprints(old_fp, new_fp)
        assert result.change_level == "STRUCTURAL"
