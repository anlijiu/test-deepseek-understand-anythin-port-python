"""PluginRegistry tests — parser registration, lookup, and dispatch."""

from __future__ import annotations

import pytest

from understand_anything.plugins.parsers import register_all_parsers
from understand_anything.plugins.parsers.dockerfile import DockerfileParser
from understand_anything.plugins.parsers.env import EnvParser
from understand_anything.plugins.parsers.graphql import GraphQLParser
from understand_anything.plugins.parsers.json_config import JSONConfigParser
from understand_anything.plugins.parsers.makefile import MakefileParser
from understand_anything.plugins.parsers.markdown import MarkdownParser
from understand_anything.plugins.parsers.protobuf import ProtobufParser
from understand_anything.plugins.parsers.shell import ShellParser
from understand_anything.plugins.parsers.sql import SQLParser
from understand_anything.plugins.parsers.terraform import TerraformParser
from understand_anything.plugins.parsers.toml_config import TOMLParser
from understand_anything.plugins.parsers.yaml_config import YAMLConfigParser
from understand_anything.plugins.registry import PluginRegistry
from understand_anything.plugins.tree_sitter import TreeSitterPlugin


class TestPluginRegistry:
    """Tests for PluginRegistry — registration and lookup."""

    def test_empty_registry_has_no_plugins(self):
        """A fresh registry has zero plugins and zero languages."""
        registry = PluginRegistry()
        assert registry.plugin_count == 0
        assert registry.language_count == 0
        assert registry.get_plugins() == []
        assert registry.get_supported_languages() == []

    def test_register_single_parser(self):
        """Register a single parser and verify it is indexed by languages."""
        registry = PluginRegistry()
        parser = MarkdownParser()
        registry.register(parser)

        assert registry.plugin_count == 1
        assert registry.language_count == 1
        assert "markdown" in registry.get_supported_languages()
        assert registry.get_plugin_for_language("markdown") is parser

    def test_register_multi_language_parser(self):
        """A parser with multiple languages registers all of them."""
        registry = PluginRegistry()
        parser = EnvParser()
        # verify env parser only has one language, so use a multi-lang one
        registry.register(ShellParser())  # ["shell", "jenkinsfile"]

        assert "shell" in registry.get_supported_languages()
        assert "jenkinsfile" in registry.get_supported_languages()
        assert registry.get_plugin_for_language("shell") is not None
        assert registry.get_plugin_for_language("jenkinsfile") is not None

    def test_register_all_12_parsers(self):
        """``register_all_parsers(registry)`` registers exactly 12 parsers."""
        registry = PluginRegistry()
        plugins = register_all_parsers(registry)

        assert len(plugins) == 12
        assert registry.plugin_count == 12

    def test_all_parser_languages_are_resolvable(self):
        """Every language declared by the 12 parsers resolves to a plugin."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        expected_languages = {
            "markdown",
            "yaml", "kubernetes", "docker-compose", "github-actions", "openapi",
            "json", "jsonc", "json-schema",
            "toml",
            "env",
            "dockerfile",
            "sql",
            "graphql",
            "protobuf",
            "terraform",
            "makefile",
            "shell", "jenkinsfile",
        }

        supported = set(registry.get_supported_languages())
        for lang in expected_languages:
            assert lang in supported, f"Language '{lang}' not in registry"
            plugin = registry.get_plugin_for_language(lang)
            assert plugin is not None, f"No plugin resolved for '{lang}'"

    def test_unregister_removes_parser(self):
        """``unregister`` removes a plugin and rebuilds the language map."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        registry.unregister("sql-parser")
        assert "sql" not in registry.get_supported_languages()
        assert registry.get_plugin_for_language("sql") is None
        assert registry.plugin_count == 11

    def test_unregister_nonexistent_is_noop(self):
        """Unregistering an unknown name does nothing."""
        registry = PluginRegistry()
        register_all_parsers(registry)
        registry.unregister("nonexistent-parser")
        assert registry.plugin_count == 12

    def test_last_registered_plugin_wins_for_language(self):
        """When two plugins claim the same language, the last one wins."""
        registry = PluginRegistry()
        first = MarkdownParser()
        second = YAMLConfigParser()  # does NOT claim "markdown"

        registry.register(first)
        registry.register(second)

        # "markdown" still resolves to first (second doesn't claim it)
        assert registry.get_plugin_for_language("markdown") is first
        assert registry.get_plugin_for_language("yaml") is second

    def test_duplicate_language_registration_last_wins(self):
        """When two plugins CLAIM the same language, last register wins."""
        registry = PluginRegistry()

        class FakeMarkdownA(MarkdownParser):
            name = "fake-a"

        class FakeMarkdownB(MarkdownParser):
            name = "fake-b"

        a = FakeMarkdownA()
        b = FakeMarkdownB()
        registry.register(a)
        registry.register(b)

        # Both claim "markdown", last one registered (b) should win
        assert registry.get_plugin_for_language("markdown") is b

    def test_registry_returns_list_without_registry(self):
        """``register_all_parsers()`` without a registry still returns the list."""
        plugins = register_all_parsers()
        assert len(plugins) == 12


class TestPluginRegistryFileResolution:
    """Tests for file-path-based plugin resolution."""

    def test_resolves_by_extension(self):
        """File extension maps to correct parser via built-in mapping."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        # Code extensions (no plugin registered unless TreeSitterPlugin is added)
        # Non-code extensions
        assert isinstance(
            registry.get_plugin_for_file("README.md"), MarkdownParser
        )
        assert isinstance(
            registry.get_plugin_for_file("config.yaml"), YAMLConfigParser
        )
        assert isinstance(
            registry.get_plugin_for_file("package.json"), JSONConfigParser
        )
        assert isinstance(
            registry.get_plugin_for_file("pyproject.toml"), TOMLParser
        )
        assert isinstance(
            registry.get_plugin_for_file(".env"), EnvParser
        )
        assert isinstance(
            registry.get_plugin_for_file("schema.sql"), SQLParser
        )
        assert isinstance(
            registry.get_plugin_for_file("schema.graphql"), GraphQLParser
        )
        assert isinstance(
            registry.get_plugin_for_file("user.proto"), ProtobufParser
        )
        assert isinstance(
            registry.get_plugin_for_file("main.tf"), TerraformParser
        )
        assert isinstance(
            registry.get_plugin_for_file("script.sh"), ShellParser
        )

    def test_resolves_by_filename(self):
        """Filename-based lookup works for Dockerfile, Makefile, Jenkinsfile."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        assert isinstance(
            registry.get_plugin_for_file("Dockerfile"), DockerfileParser
        )
        assert isinstance(
            registry.get_plugin_for_file("path/to/Dockerfile"), DockerfileParser
        )
        assert isinstance(
            registry.get_plugin_for_file("Makefile"), MakefileParser
        )
        assert isinstance(
            registry.get_plugin_for_file("Jenkinsfile"), ShellParser
        )

    def test_unknown_extension_returns_none(self):
        """Files with unknown extensions return None."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        assert registry.get_plugin_for_file("data.xyz") is None
        assert registry.get_plugin_for_file("random.bin") is None


class TestPluginRegistryDispatch:
    """Tests for dispatch methods (analyze, resolve_imports, etc.)."""

    def test_analyze_file_dispatches_to_correct_parser(self):
        """``analyze_file`` dispatches to the right parser by file path."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        analysis = registry.analyze_file("test.md", "# Hello\n\nContent.")
        assert analysis is not None
        assert len(analysis.sections) == 1
        assert analysis.sections[0].name == "Hello"

    def test_analyze_file_returns_none_for_unknown_type(self):
        """Analyzing an unknown file type returns None."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        assert registry.analyze_file("data.xyz", "content") is None

    def test_extract_references_dispatches_to_correct_parser(self):
        """``extract_references`` dispatches to the right parser."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        content = "# Doc\n\nSee [guide](./guide.md)\n"
        refs = registry.extract_references("docs/index.md", content)
        assert refs is not None
        assert len(refs) >= 1
        assert any(r.target == "./guide.md" for r in refs)

    def test_extract_references_returns_empty_for_default_implementation(self):
        """If a parser uses the default extract_references, returns empty list."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        # YAML parser does not override extract_references (uses ABC default)
        refs = registry.extract_references("config.yaml", "key: val")
        assert refs == []

    def test_get_plugins_returns_registration_order(self):
        """``get_plugins`` returns plugins in the order they were registered."""
        registry = PluginRegistry()
        register_all_parsers(registry)

        plugins = registry.get_plugins()
        assert len(plugins) == 12
        # First registered should be MarkdownParser, last ShellParser
        assert isinstance(plugins[0], MarkdownParser)
        assert isinstance(plugins[-1], ShellParser)


# ---------------------------------------------------------------------------
# PluginRegistry + TreeSitterPlugin 集成测试
# ---------------------------------------------------------------------------


_SAMPLE_SRC: dict[str, str] = {
    "python": "def hello():\n    return 42\n",
    "tsx": "function hello(): number { return 42; }\n",
    "typescript": "function hello(): number { return 42; }\n",
    "javascript": "function hello() { return 42; }\n",
    "c": "int add(int a, int b) { return a + b; }\n",
    "cpp": "int add(int a, int b) { return a + b; }\n",
    "java": "public class Hello { public int getValue() { return 1; } }\n",
}


class TestRegistryTreeSitterIntegration:
    """PluginRegistry 注册 TreeSitterPlugin 后的分发集成测试。"""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        r = PluginRegistry()
        r.register(TreeSitterPlugin())
        return r

    # -- 所有代码扩展名的分发路径 ------------------------------------------

    @pytest.mark.parametrize(
        ("file_path", "lang"),
        (
            (".ts", "typescript"),
            (".tsx", "tsx"),
            (".js", "javascript"),
            (".jsx", "javascript"),
            (".mjs", "javascript"),
            (".cjs", "javascript"),
            (".mts", "typescript"),
            (".cts", "typescript"),
            (".py", "python"),
            (".pyi", "python"),
            (".pyw", "python"),
            (".java", "java"),
            (".c", "c"),
            (".h", "c"),
            (".cpp", "cpp"),
            (".cc", "cpp"),
            (".cxx", "cpp"),
            (".c++", "cpp"),
            (".hpp", "cpp"),
            (".hh", "cpp"),
            (".hxx", "cpp"),
            (".h++", "cpp"),
        ),
    )
    def test_registry_analyzes_all_code_extensions(
        self, registry: PluginRegistry, file_path: str, lang: str
    ) -> None:
        """所有代码扩展名经 registry → TreeSitterPlugin 分发后均能成功分析。"""
        result = registry.analyze_file(
            f"test{file_path}", _SAMPLE_SRC[lang]
        )
        assert result is not None
        assert isinstance(result.functions, list)

    # -- 之前不匹配的关键案例 -----------------------------------------------

    def test_pyi_dispatches_to_tree_sitter_and_succeeds(
        self, registry: PluginRegistry,
    ) -> None:
        """.pyi 文件：registry 映射到 "python"→TreeSitterPlugin，
        TreeSitterPlugin._detect_language 也识别为 "python"，分析成功。"""
        src = "def hello():\n    ...\n"
        result = registry.analyze_file("stub.pyi", src)
        assert result is not None
        assert len(result.functions) >= 1
        assert result.functions[0].name == "hello"

    def test_h_dispatches_consistently(
        self, registry: PluginRegistry,
    ) -> None:
        """.h 文件：registry 映射到 "c"，TreeSitterPlugin._detect_language
        也映射到 "c"，两者一致，分析成功。"""
        src = "int add(int a, int b);\n"
        result = registry.analyze_file("header.h", src)
        assert result is not None
        assert isinstance(result.functions, list)

    # -- registry 分发失败的用例 --------------------------------------------

    def test_unknown_code_extension_returns_none(
        self, registry: PluginRegistry,
    ) -> None:
        """未注册的代码扩展名（如 .go）不经过 registry 分发，直接返回 None。"""
        # .go 不在 registry 的 _BUILTIN_EXTENSION_MAP 中
        assert registry.get_plugin_for_file("test.go") is None
        assert registry.analyze_file("test.go", "package main\n") is None

    def test_unknown_extension_does_not_crash_plugin(
        self, registry: PluginRegistry,
    ) -> None:
        """registry 匹配到 TreeSitterPlugin，但插件 re-detect 为 "unknown"
        时应优雅报错（而非静默返回 None 或崩溃）。

        注：当前 .rs 不在 registry 映射中 → get_plugin_for_file 返回 None →
        analyze_file 返回 None。如果将来 registry 映射扩展了 .rs→"rust"，
        但 TreeSitterPlugin 不支持 "rust"，则会进入插件内 ValueError。
        """
        # 当前行为：.rs 不在 registry 映射 → None
        result = registry.analyze_file("test.rs", "fn main() {}\n")
        assert result is None
