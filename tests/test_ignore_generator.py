"""Tests for .understandignore generator."""

from __future__ import annotations

from pathlib import Path

from understand_anything.ignore.generator import (
    generate_starter_ignore_file,
    generate_understandignore,
    guess_ignore_rules,
)


class TestGuessIgnoreRules:
    def test_returns_language_patterns(self) -> None:
        rules = guess_ignore_rules(languages=["python"])
        assert "__pycache__" in rules
        assert "*.pyc" in rules
        assert ".venv" in rules

    def test_returns_framework_patterns(self) -> None:
        rules = guess_ignore_rules(frameworks=["django"])
        assert "*.sqlite3" in rules
        assert "staticfiles" in rules

    def test_combines_both(self) -> None:
        rules = guess_ignore_rules(languages=["python", "javascript"], frameworks=["react"])
        assert "__pycache__" in rules
        assert "node_modules" in rules
        assert "build" in rules  # from react

    def test_deduplicates(self) -> None:
        # "build" appears in both python and javascript
        rules = guess_ignore_rules(languages=["python", "javascript"])
        assert rules.count("build") == 1

    def test_includes_large_files(self) -> None:
        rules = guess_ignore_rules(large_files=["big_data.json", "dump.sql"])
        assert "big_data.json" in rules
        assert "dump.sql" in rules

    def test_empty_returns_empty_list(self) -> None:
        assert guess_ignore_rules() == []

    def test_sorted_output(self) -> None:
        rules = guess_ignore_rules(languages=["rust", "go"])
        assert rules == sorted(rules)

    def test_unknown_language_ignored_gracefully(self) -> None:
        rules = guess_ignore_rules(languages=["brainfuck"])
        assert rules == []


class TestGenerateUnderstandignore:
    def test_generates_file(self, tmp_path: Path) -> None:
        target = generate_understandignore(
            tmp_path,
            project_name="test-project",
            languages=["python"],
        )
        assert target.is_file()
        content = target.read_text()
        assert "test-project" in content
        assert "__pycache__" in content
        assert "*.pyc" in content

    def test_no_overwrite_by_default(self, tmp_path: Path) -> None:
        ui_path = tmp_path / ".understandignore"
        ui_path.write_text("original content")
        target = generate_understandignore(tmp_path, languages=["python"])
        assert target.read_text() == "original content"

    def test_overwrite_flag(self, tmp_path: Path) -> None:
        ui_path = tmp_path / ".understandignore"
        ui_path.write_text("original content")
        target = generate_understandignore(
            tmp_path, languages=["go"], overwrite=True
        )
        assert "vendor" in target.read_text()

    def test_empty_languages_produces_header_only(self, tmp_path: Path) -> None:
        target = generate_understandignore(tmp_path)
        content = target.read_text()
        assert content.strip().startswith("#")
        # No patterns, just header
        assert "__pycache__" not in content


class TestGenerateStarterIgnoreFile:
    def test_generates_commented_suggestions(self, tmp_path: Path) -> None:
        """生成的内容中所有非空行都应以 # 开头。"""
        (tmp_path / "tests").mkdir()
        output = generate_starter_ignore_file(tmp_path)
        non_empty_lines = [line for line in output.splitlines() if line.strip()]
        assert len(non_empty_lines) > 0
        for line in non_empty_lines:
            assert line.startswith("#"), f"Line does not start with #: {line!r}"

    def test_scans_gitignore(self, tmp_path: Path) -> None:
        """项目有 .gitignore 时，非默认规则应出现在 starter 中且被注释。"""
        (tmp_path / ".gitignore").write_text(
            "node_modules\nlogs/\ncustom_output/\n"
        )
        output = generate_starter_ignore_file(tmp_path)
        # 应有 From .gitignore 段落标题（对标 TS）
        assert "# --- From .gitignore (uncomment to exclude) ---" in output
        # logs/ 是自定义规则，应在输出中以注释形式出现
        assert "# logs/" in output
        # custom_output/ 也是自定义规则
        assert "# custom_output/" in output

    def test_detects_common_dirs(self, tmp_path: Path) -> None:
        """存在 tests/、docs/ 目录时应出现在 Detected directories 段落。"""
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        output = generate_starter_ignore_file(tmp_path)
        assert "# --- Detected directories (uncomment to exclude) ---" in output
        assert "# tests/" in output
        assert "# docs/" in output

    def test_default_covered_rules_not_repeated(self, tmp_path: Path) -> None:
        """已被 DEFAULT_IGNORE_PATTERNS 覆盖的 .gitignore 规则不应重复建议。"""
        # node_modules 已在 DEFAULT_IGNORE_PATTERNS 中
        (tmp_path / ".gitignore").write_text("node_modules\n.env\n")
        output = generate_starter_ignore_file(tmp_path)
        # .env 不在默认规则中，应出现在建议中
        assert "# .env" in output
        # node_modules 在默认规则中，不应建议
        assert "# node_modules" not in output

    def test_trailing_slash_normalization_gitignore(self, tmp_path: Path) -> None:
        """dist/ 与 dist、coverage 与 coverage/ 应视为已覆盖的等价规则。"""
        (tmp_path / ".gitignore").write_text(
            "dist/\ncoverage\nbuild/\nlogs/\n"
        )
        output = generate_starter_ignore_file(tmp_path)
        # dist 已在 DEFAULT_IGNORE_PATTERNS 中，dist/ 不应建议
        assert "# dist/" not in output
        # coverage/ 已在 DEFAULT_IGNORE_PATTERNS 中，coverage 不应建议
        assert "# coverage" not in output
        # build 在默认中，build/ 不应建议
        assert "# build/" not in output
        # logs/ 不在默认中，应建议
        assert "# logs/" in output

    def test_empty_project_always_has_test_section(self, tmp_path: Path) -> None:
        """无 .gitignore 无特殊目录时仍会生成 Header + 通用测试模式段落。"""
        output = generate_starter_ignore_file(tmp_path)
        # 应有 Header（核对 TS HEADER 字符串）
        assert "patterns for files/dirs to exclude from analysis" in output
        assert "Built-in defaults" in output
        # 不应含 gitignore 和目录段落标题
        assert "From .gitignore" not in output
        assert "Detected directories" not in output
        # 但通用测试模式段落总是生成
        assert "# --- Test file patterns (uncomment to exclude) ---" in output
        assert "# *.test.*" in output
        assert "# *.spec.*" in output
        assert "# *.snap" in output

    def test_emits_generic_test_patterns_unconditionally(
        self, tmp_path: Path
    ) -> None:
        """无论项目内容如何，*.test.*、*.spec.*、*.snap 总是出现在输出中。"""
        # 空项目
        output = generate_starter_ignore_file(tmp_path)
        assert "# *.test.*" in output
        assert "# *.spec.*" in output
        assert "# *.snap" in output
        # 有 .gitignore 和目录的项目
        (tmp_path / ".gitignore").write_text("logs/\n")
        (tmp_path / "tests").mkdir()
        output2 = generate_starter_ignore_file(tmp_path)
        assert "# *.test.*" in output2
        assert "# *.spec.*" in output2
        assert "# *.snap" in output2

    def test_output_is_string_not_file(self, tmp_path: Path) -> None:
        """返回 str 类型，不写入文件。"""
        (tmp_path / "tests").mkdir()
        result = generate_starter_ignore_file(tmp_path)
        assert isinstance(result, str)
        assert not (tmp_path / ".understandignore").exists()

    def test_detects_all_ts_dirs(self, tmp_path: Path) -> None:
        """所有 TS DETECTABLE_DIRS 中的目录如果存在都应被检测到。"""
        ts_dirs = [
            "__tests__", "test", "tests", "fixtures", "testdata",
            "docs", "examples", "scripts", "migrations", ".storybook",
        ]
        for d in ts_dirs:
            (tmp_path / d).mkdir()
        output = generate_starter_ignore_file(tmp_path)
        for d in ts_dirs:
            assert f"# {d}/" in output, f"Missing suggestion for dir: {d}/"
