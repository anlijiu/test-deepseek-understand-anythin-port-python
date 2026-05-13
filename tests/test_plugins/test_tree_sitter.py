"""TreeSitterPlugin 集成测试。

覆盖 ``analyze_file()`` 成功/失败路径、``register_extractor()``
在无 grammar 时的失败语义，以及 grammar 注册 API。
"""

from __future__ import annotations

import pytest

from understand_anything.plugins.extractors.python import PythonExtractor
from understand_anything.plugins.extractors.types import ExtractorRegistration
from understand_anything.plugins.tree_sitter import (
    PY_LANGUAGE,
    SUPPORTED_TREE_SITTER_LANGUAGES,
    TreeSitterPlugin,
)


class TestAnalyzeFileSuccess:
    """``analyze_file()`` 对所有内置支持语言的成功路径。"""

    # -- 每种语言最小可用源码 ------------------------------------------------

    PYTHON_SRC = "def hello():\n    return 42\n"
    TYPESCRIPT_SRC = "function hello(): number { return 42; }\n"
    TSX_SRC = (
        "import React from 'react';\n"
        "const App = () => <div>hello</div>;\n"
        "export default App;\n"
    )
    JAVASCRIPT_SRC = "function hello() { return 42; }\n"
    JSX_SRC = (
        "import React from 'react';\n"
        "function Header() { return <div/>; }\n"
        "export { Header };\n"
    )
    C_SRC = "int add(int a, int b) { return a + b; }\n"
    CPP_SRC = "int add(int a, int b) { return a + b; }\n"
    JAVA_SRC = "public class Hello { public int getValue() { return 1; } }\n"

    @pytest.fixture(scope="class")
    def plugin(self) -> TreeSitterPlugin:
        return TreeSitterPlugin()

    def test_analyze_python(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.py", self.PYTHON_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "hello"

    def test_analyze_typescript(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.ts", self.TYPESCRIPT_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "hello"

    def test_analyze_tsx(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.tsx", self.TSX_SRC)
        # TSX 可以解析，验证不会抛异常即可
        assert result is not None

    def test_analyze_javascript(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.js", self.JAVASCRIPT_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "hello"

    def test_analyze_jsx(self, plugin: TreeSitterPlugin) -> None:
        """.jsx 文件使用 tree-sitter-javascript grammar + TypeScriptExtractor。

        ``function`` 声明组件可被正确提取，``const Arrow = () => <jsx/>``
        目前不被识别为函数（extractor 层面限制，非 grammar 问题）。
        """
        result = plugin.analyze_file("test.jsx", self.JSX_SRC)
        assert result is not None
        assert len(result.functions) >= 1
        assert result.functions[0].name == "Header"

    def test_analyze_c(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.c", self.C_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "add"

    def test_analyze_cpp(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.cpp", self.CPP_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "add"

    def test_analyze_java(self, plugin: TreeSitterPlugin) -> None:
        result = plugin.analyze_file("test.java", self.JAVA_SRC)
        assert len(result.classes) >= 1
        assert result.classes[0].name == "Hello"


class TestAnalyzeFileUnsupported:
    """``analyze_file()`` 对尚未实现 extractor/grammar 的语言应报错。"""

    @pytest.fixture(scope="class")
    def plugin(self) -> TreeSitterPlugin:
        return TreeSitterPlugin()

    @pytest.mark.parametrize(
        ("file_path", "ext_label"),
        (
            ("test.go", ".go"),
            ("test.rs", ".rs"),
            ("test.rb", ".rb"),
            ("test.php", ".php"),
            ("test.cs", ".cs"),
        ),
    )
    def test_unsupported_extension_raises_value_error(
        self, plugin: TreeSitterPlugin, file_path: str, ext_label: str
    ) -> None:
        """未支持的扩展名应抛出 ValueError（'unknown' 没有注册 extractor）。"""
        with pytest.raises(ValueError, match="No extractor registered for language"):
            plugin.analyze_file(file_path, "// dummy content\n")

    def test_all_unsupported_not_in_supported_list(self) -> None:
        """确认 .go/.rs/.rb/.php/.cs 不在 SUPPORTED_TREE_SITTER_LANGUAGES 中。"""
        unsupported_langs = {"go", "rust", "ruby", "php", "csharp"}
        for lang in unsupported_langs:
            assert lang not in SUPPORTED_TREE_SITTER_LANGUAGES


class TestRegisterExtractorWithoutGrammar:
    """``register_extractor()`` 注册 extractor 但无对应 grammar 时的失败语义。"""

    @pytest.fixture
    def plugin(self) -> TreeSitterPlugin:
        return TreeSitterPlugin()

    def test_get_parser_fails_without_grammar(self, plugin: TreeSitterPlugin) -> None:
        """注册 extractor 无法替代缺失的 grammar — get_parser() 必须报错。"""
        plugin.register_extractor("go", PythonExtractor())
        assert "go" in plugin.languages

        with pytest.raises(
            ValueError, match="No tree-sitter grammar registered for 'go'"
        ):
            plugin.get_parser("go")

    def test_grammar_error_for_any_unsupported_language(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """即使注册了 extractor，任意无 grammar 的 language_id 都应触发
        ``_get_grammar`` 的 ValueError。"""
        plugin.register_extractor("rust", PythonExtractor())

        with pytest.raises(ValueError, match="tree-sitter grammar"):
            plugin.get_parser("rust")

    def test_register_extractor_does_not_add_grammar(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """``register_extractor`` 只注册 extractor，不自动添加 grammar。"""
        original_count = len(plugin.languages)
        plugin.register_extractor("go", PythonExtractor())
        # languages 确实增加了
        assert len(plugin.languages) == original_count + 1
        # 但 grammar 缺失 — get_parser 会报错
        with pytest.raises(ValueError, match="grammar"):
            plugin.get_parser("go")

    def test_register_then_analyze_file_fails_on_grammar(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """注册 extractor 后 analyze_file 仍失败，因为 _detect_language
        无法将未知扩展名映射到已注册的 language_id。

        关键点：外部注册的 extractor 语言 ID 必须同时满足两个条件才能被
        ``analyze_file`` 使用：
        1. 在 ``_extractors`` 中已注册；
        2. 文件扩展名能被 ``_detect_language()`` 映射到该 language_id；
        3. 在 ``_LANGUAGE_GRAMMARS`` 中有对应 grammar。
        """
        plugin.register_extractor("php", PythonExtractor())
        # .php 不在 _detect_language 的扩展名映射表中 → 检测为 "unknown"
        with pytest.raises(ValueError, match="No extractor registered"):
            plugin.analyze_file("test.php", "<?php echo 1;")


class TestRegisterGrammar:
    """``register_grammar`` / ``register_language`` 的 grammar 注册 API 测试。"""

    @pytest.fixture
    def plugin(self) -> TreeSitterPlugin:
        return TreeSitterPlugin()

    # -- register_grammar + register_extractor ---------------------------------

    def test_register_grammar_and_extractor_enables_get_parser(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """``register_grammar`` + ``register_extractor`` 后 get_parser 成功。"""
        plugin.register_grammar("go", PY_LANGUAGE)
        plugin.register_extractor("go", PythonExtractor())

        parser = plugin.get_parser("go")
        tree = parser.parse(b"def hello(): pass")
        assert tree.root_node is not None

    def test_register_extractor_with_grammar_arg(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """``register_extractor`` 的 ``grammar`` 参数等价于分别调用。"""
        plugin.register_extractor("go", PythonExtractor(), grammar=PY_LANGUAGE)

        parser = plugin.get_parser("go")
        assert parser is not None

    # -- register_language 便捷方法 --------------------------------------------

    def test_register_language_registers_both(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """``register_language`` 同时注册 grammar 和 extractor。"""
        plugin.register_language("go", PY_LANGUAGE, PythonExtractor())

        assert "go" in plugin.languages
        parser = plugin.get_parser("go")
        tree = parser.parse(b"def hello(): pass")
        assert tree.root_node is not None

    # -- ExtractorRegistration 携带 grammar -----------------------------------

    def test_extra_extractors_with_grammar(
        self,
    ) -> None:
        """通过 ``extra_extractors`` 传入带 grammar 的 ``ExtractorRegistration``。"""
        plugin = TreeSitterPlugin(
            extra_extractors=[
                ExtractorRegistration(
                    language_id="go",
                    extractor=PythonExtractor(),
                    grammar=PY_LANGUAGE,
                ),
            ],
        )
        assert "go" in plugin.languages
        parser = plugin.get_parser("go")
        assert parser is not None

    # -- grammar-only 缺 extractor 的场景 --------------------------------------

    def test_register_grammar_without_extractor(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """只注册 grammar 不注册 extractor — get_parser 成功，但 languages 不含该 ID。"""
        plugin.register_grammar("go", PY_LANGUAGE)
        # grammar 就位了，parser 可用
        parser = plugin.get_parser("go")
        assert parser is not None
        # 但没有 extractor，languages 不包含 "go"
        assert "go" not in plugin.languages

    # -- 实例隔离 -------------------------------------------------------------

    def test_grammar_registration_is_instance_scoped(
        self,
    ) -> None:
        """一个实例注册的 grammar 不会影响另一个实例。"""
        plugin_a = TreeSitterPlugin()
        plugin_b = TreeSitterPlugin()

        plugin_a.register_grammar("go", PY_LANGUAGE)
        plugin_a.register_extractor("go", PythonExtractor())

        # plugin_a 可以获取 parser
        assert plugin_a.get_parser("go") is not None

        # plugin_b 不受影响
        with pytest.raises(
            ValueError, match="No tree-sitter grammar registered for 'go'"
        ):
            plugin_b.get_parser("go")

    def test_instance_grammar_overrides_module_level(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """实例级 grammar 可以覆盖模块级 ``_LANGUAGE_GRAMMARS``。"""
        # python 语言已有内置 grammar，但我们可以注册一个不同的 grammar 覆盖它
        plugin.register_grammar("python", PY_LANGUAGE)
        parser = plugin.get_parser("python")
        assert parser is not None
        # 验证依然能正常解析
        tree = parser.parse(b"def hello(): pass")
        assert tree.root_node is not None

    def test_grammar_override_invalidates_cached_parser(
        self, plugin: TreeSitterPlugin,
    ) -> None:
        """先调用 get_parser 缓存旧 parser，再注册替换 grammar，
        后续 get_parser 必须返回新 parser 而非缓存的旧对象。"""
        # 步骤 1：触发 parser 创建 & 缓存（使用模块级内置 grammar）
        old_parser = plugin.get_parser("python")
        assert old_parser is not None

        # 步骤 2：用实例级 grammar 覆盖
        plugin.register_grammar("python", PY_LANGUAGE)

        # 步骤 3：再次获取 parser — 必须是新对象（缓存已清除）
        new_parser = plugin.get_parser("python")
        assert new_parser is not None
        assert new_parser is not old_parser, (
            "grammar override must invalidate cached parser"
        )


class TestRegisterLanguageFullExtension:
    """``register_language`` / ``register_extractor`` 携带 extensions/filenames
    后 ``analyze_file`` 能正确分发到新语言。
    """

    PYTHON_SRC = "def hello():\n    return 42\n"

    # -- register_language + extensions → analyze_file 成功 ------------------

    def test_register_language_with_extensions_enables_analyze_file(
        self,
    ) -> None:
        """``register_language`` 附带 extensions 后 analyze_file 能识别新语言。"""
        plugin = TreeSitterPlugin()
        plugin.register_language(
            "go", PY_LANGUAGE, PythonExtractor(), extensions=[".go"]
        )

        result = plugin.analyze_file("main.go", self.PYTHON_SRC)
        assert len(result.functions) >= 1
        assert result.functions[0].name == "hello"

    def test_register_extractor_with_extensions_enables_analyze_file(
        self,
    ) -> None:
        """``register_extractor`` 附带 grammar + extensions 后 analyze_file 成功。"""
        plugin = TreeSitterPlugin()
        plugin.register_extractor(
            "rust", PythonExtractor(), grammar=PY_LANGUAGE, extensions=[".rs"]
        )

        result = plugin.analyze_file("lib.rs", self.PYTHON_SRC)
        assert len(result.functions) >= 1

    # -- 多个扩展名 ---------------------------------------------------------

    def test_multiple_extensions_for_one_language(
        self,
    ) -> None:
        """一个语言可以注册多个扩展名。"""
        plugin = TreeSitterPlugin()
        plugin.register_language(
            "ruby", PY_LANGUAGE, PythonExtractor(),
            extensions=[".rb", ".rbw"],
        )
        result = plugin.analyze_file("script.rb", self.PYTHON_SRC)
        assert result.functions[0].name == "hello"

        result2 = plugin.analyze_file("script.rbw", self.PYTHON_SRC)
        assert result2.functions[0].name == "hello"

    # -- 文件名映射（非扩展名场景） ------------------------------------------

    def test_filename_based_mapping(
        self,
    ) -> None:
        """``filenames`` 参数支持精确文件名匹配（如 Makefile）。"""
        plugin = TreeSitterPlugin()
        plugin.register_language(
            "makefile", PY_LANGUAGE, PythonExtractor(),
            filenames=["Makefile", "GNUmakefile"],
        )
        result = plugin.analyze_file("Makefile", "all: build\n")
        assert result is not None

    def test_filename_case_insensitive(
        self,
    ) -> None:
        """文件名映射大小写不敏感。"""
        plugin = TreeSitterPlugin()
        plugin.register_language(
            "dockerfile", PY_LANGUAGE, PythonExtractor(),
            filenames=["Dockerfile"],
        )
        result = plugin.analyze_file("dockerfile", "FROM python:3\n")
        assert result is not None

    # -- ExtractorRegistration 携带 extensions -------------------------------

    def test_extra_extractors_with_extensions(
        self,
    ) -> None:
        """通过 ``extra_extractors`` 传入带 extensions 的 ``ExtractorRegistration``。"""
        plugin = TreeSitterPlugin(
            extra_extractors=[
                ExtractorRegistration(
                    language_id="go",
                    extractor=PythonExtractor(),
                    grammar=PY_LANGUAGE,
                    extensions=[".go"],
                ),
            ],
        )
        result = plugin.analyze_file("main.go", self.PYTHON_SRC)
        assert len(result.functions) >= 1

    def test_extra_extractors_with_filenames(
        self,
    ) -> None:
        """通过 ``extra_extractors`` 传入带 filenames 的 ``ExtractorRegistration``。"""
        plugin = TreeSitterPlugin(
            extra_extractors=[
                ExtractorRegistration(
                    language_id="make",
                    extractor=PythonExtractor(),
                    grammar=PY_LANGUAGE,
                    filenames=["Makefile"],
                ),
            ],
        )
        result = plugin.analyze_file("Makefile", "all:\n\techo done\n")
        assert result is not None

    # -- extensions 不带 grammar 时正确报错 ---------------------------------

    def test_extensions_without_grammar_still_fails(
        self,
    ) -> None:
        """只注册 extensions + extractor 但不注册 grammar，
        analyze_file 应在 get_parser 阶段报错。
        """
        plugin = TreeSitterPlugin()
        plugin.register_extractor("go", PythonExtractor(), extensions=[".go"])

        with pytest.raises(ValueError, match="tree-sitter grammar"):
            plugin.analyze_file("main.go", self.PYTHON_SRC)

    # -- 实例隔离 -----------------------------------------------------------

    def test_extension_map_is_instance_scoped(
        self,
    ) -> None:
        """一个实例注册的扩展名映射不影响另一个实例。"""
        plugin_a = TreeSitterPlugin()
        plugin_b = TreeSitterPlugin()

        plugin_a.register_language(
            "go", PY_LANGUAGE, PythonExtractor(), extensions=[".go"]
        )
        # plugin_a 能分析 .go 文件
        assert plugin_a.analyze_file("main.go", self.PYTHON_SRC) is not None

        # plugin_b 不受影响 — .go 仍然是 "unknown"
        with pytest.raises(ValueError, match="No extractor registered"):
            plugin_b.analyze_file("main.go", "package main\n")

    def test_instance_extension_overrides_builtin(
        self,
    ) -> None:
        """实例级扩展名映射可以覆盖内置的扩展名 → 语言 ID 映射。"""
        plugin = TreeSitterPlugin()
        # .py 内置映射到 "python"，但我们可以重映射它
        plugin.register_language(
            "custom_py", PY_LANGUAGE, PythonExtractor(),
            extensions=[".py"],
        )
        assert "custom_py" in plugin.languages
        # analyze_file 仍能工作，因为 extractor 和 grammar 都可用
        result = plugin.analyze_file("test.py", self.PYTHON_SRC)
        assert result is not None
