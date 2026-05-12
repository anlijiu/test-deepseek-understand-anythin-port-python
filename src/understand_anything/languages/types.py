"""Language and framework configuration type definitions.

Python port of the TypeScript ``LanguageConfig`` and ``FrameworkConfig`` Zod
schemas from ``@understand-anything/core/src/languages/types.ts``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TreeSitterConfig(BaseModel):
    """Tree-sitter 语法包加载配置。

    Python 版本不需要此配置（语言包直接通过 Python 模块加载），
    但保留此模型用于和 TypeScript 版本保持数据结构兼容。
    """

    wasm_package: str = Field(alias="wasmPackage")
    """npm 包名（Python 版本中仅为参考信息）。"""

    wasm_file: str = Field(alias="wasmFile")
    """WASM 文件名（Python 版本中仅为参考信息）。"""

    model_config = {"populate_by_name": True}


class FilePatternConfig(BaseModel):
    """文件模式约定 — 用于识别入口点、桶文件、测试和配置文件。"""

    entry_points: list[str] = Field(default_factory=list, alias="entryPoints")
    """入口点文件模式列表，如 ``[\"main.py\", \"src/index.ts\"]``。"""

    barrels: list[str] = Field(default_factory=list)
    """桶文件模式列表，如 ``[\"__init__.py\", \"index.ts\"]``。"""

    tests: list[str] = Field(default_factory=list)
    """测试文件模式列表，如 ``[\"test_*.py\", \"*.test.ts\"]``。"""

    config: list[str] = Field(default_factory=list)
    """配置文件模式列表，如 ``[\"pyproject.toml\", \"tsconfig.json\"]``。"""

    model_config = {"populate_by_name": True}


class LanguageConfig(BaseModel):
    """单个语言的完整配置。

    包含扩展名映射、检测文件名、tree-sitter 语法信息和文件模式约定。
    """

    id: str = Field(min_length=1)
    """机器友好标识符，如 ``\"python\"``、``\"dockerfile\"``。"""

    display_name: str = Field(min_length=1, alias="displayName")
    """人类可读名称，如 ``\"Python\"``、``\"Dockerfile\"``。"""

    extensions: list[str]
    """文件扩展名列表（含点），如 ``[\".py\", \".pyi\"]``。
    纯文件名检测的语言可以为空列表。"""

    filenames: list[str] | None = None
    """精确文件名列表（用于 Dockerfile、Makefile 等无扩展名文件）。
    可为 ``None`` 表示不按文件名检测。"""

    tree_sitter: TreeSitterConfig | None = Field(default=None, alias="treeSitter")
    """Tree-sitter 语法加载配置。没有 tree-sitter 语法的语言为 ``None``。"""

    concepts: list[str]
    """语言特有概念/惯用法的字符串列表，如 ``[\"goroutines\", \"channels\"]``。"""

    file_patterns: FilePatternConfig = Field(alias="filePatterns")
    """文件模式约定（入口点、桶文件、测试、配置）。"""

    model_config = {"populate_by_name": True}


class StrictLanguageConfig(LanguageConfig):
    """严格语言配置 — 要求至少有一个扩展名或文件名方可检测。

    某些内置配置（如 kubernetes、github-actions）Intentionally 没有扩展名
    和文件名，仅用于将来的内容检测。
    """

    @model_validator(mode="after")
    def check_detectable(self) -> StrictLanguageConfig:
        """验证至少有一个扩展名或文件名可检测。"""
        if not self.extensions and not self.filenames:
            raise ValueError(
                "LanguageConfig must have at least one extension or filename for detection"
            )
        return self

    model_config = {"populate_by_name": True}


class FrameworkConfig(BaseModel):
    """框架配置 — 用于从清单文件中检测框架。

    包含检测关键词、清单文件列表和层次结构提示。
    """

    id: str = Field(min_length=1)
    """机器友好标识符，如 ``\"django\"``、``\"react\"``。"""

    display_name: str = Field(min_length=1, alias="displayName")
    """人类可读名称，如 ``\"Django\"``、``\"React\"``。"""

    languages: list[str] = Field(min_length=1)
    """适用语言 ID 列表，每个 ID 不能为空。"""

    @model_validator(mode="after")
    def check_language_items_non_empty(self) -> FrameworkConfig:
        """验证 languages 列表中的每个元素非空。"""
        for i, lang in enumerate(self.languages):
            if not lang or not lang.strip():
                raise ValueError(f"languages[{i}] must be a non-empty string")
        return self

    detection_keywords: list[str] = Field(min_length=1, alias="detectionKeywords")
    """在清单文件内容中搜索的关键词列表（大小写不敏感）。"""

    manifest_files: list[str] = Field(min_length=1, alias="manifestFiles")
    """清单文件名列表，如 ``[\"requirements.txt\", \"package.json\"]``。"""

    prompt_snippet_path: str = Field(min_length=1, alias="promptSnippetPath")
    """框架相关 LLM 指导 Markdown 文件的路径。"""

    entry_points: list[str] | None = Field(default=None, alias="entryPoints")
    """框架典型入口点文件模式列表。可选。"""

    layer_hints: dict[str, str] | None = Field(default=None, alias="layerHints")
    """目录/文件命名 → 架构层次类别映射。可选。"""

    model_config = {"populate_by_name": True}
