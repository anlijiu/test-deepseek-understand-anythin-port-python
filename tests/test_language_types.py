"""Tests for LanguageConfig and FrameworkConfig Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from understand_anything.languages.types import (
    FilePatternConfig,
    FrameworkConfig,
    LanguageConfig,
    StrictLanguageConfig,
    TreeSitterConfig,
)


class TestTreeSitterConfig:
    """Tests for TreeSitterConfig model."""

    def test_valid_config(self) -> None:
        cfg = TreeSitterConfig(
            wasm_package="tree-sitter-python",
            wasm_file="tree-sitter-python.wasm",
        )
        assert cfg.wasm_package == "tree-sitter-python"
        assert cfg.wasm_file == "tree-sitter-python.wasm"

    def test_camel_case_input(self) -> None:
        """camelCase alias support for JSON interop."""
        cfg = TreeSitterConfig(
            wasmPackage="tree-sitter-python",
            wasmFile="tree-sitter-python.wasm",
        )
        assert cfg.wasm_package == "tree-sitter-python"
        assert cfg.wasm_file == "tree-sitter-python.wasm"


class TestFilePatternConfig:
    """Tests for FilePatternConfig model."""

    def test_valid_config(self) -> None:
        cfg = FilePatternConfig(
            entry_points=["main.py", "manage.py"],
            barrels=["__init__.py"],
            tests=["test_*.py", "*_test.py"],
            config=["pyproject.toml"],
        )
        assert len(cfg.entry_points) == 2
        assert cfg.barrels == ["__init__.py"]

    def test_camel_case_input(self) -> None:
        cfg = FilePatternConfig(
            entryPoints=["main.py"],
            barrels=["index.ts"],
            tests=["*.test.ts"],
            config=["tsconfig.json"],
        )
        assert cfg.entry_points == ["main.py"]
        assert cfg.barrels == ["index.ts"]
        assert cfg.tests == ["*.test.ts"]
        assert cfg.config == ["tsconfig.json"]

    def test_defaults_empty_lists(self) -> None:
        """All fields default to empty lists."""
        cfg = FilePatternConfig()
        assert cfg.entry_points == []
        assert cfg.barrels == []
        assert cfg.tests == []
        assert cfg.config == []


class TestLanguageConfig:
    """Tests for LanguageConfig model."""

    def test_minimal_valid_config(self) -> None:
        """A config with just id, displayName, extensions, concepts, filePatterns."""
        cfg = LanguageConfig(
            id="python",
            display_name="Python",
            extensions=[".py", ".pyi"],
            concepts=["decorators", "generators"],
            file_patterns=FilePatternConfig(
                entry_points=["main.py"],
            ),
        )
        assert cfg.id == "python"
        assert cfg.display_name == "Python"
        assert cfg.extensions == [".py", ".pyi"]
        assert cfg.filenames is None
        assert cfg.tree_sitter is None

    def test_full_valid_config(self) -> None:
        """A config with all fields populated."""
        cfg = LanguageConfig(
            id="typescript",
            display_name="TypeScript",
            extensions=[".ts", ".tsx"],
            filenames=[],
            tree_sitter=TreeSitterConfig(
                wasm_package="tree-sitter-typescript",
                wasm_file="tree-sitter-typescript.wasm",
            ),
            concepts=["generics", "decorators"],
            file_patterns=FilePatternConfig(
                entry_points=["src/index.ts"],
                barrels=["index.ts"],
                tests=["*.test.ts"],
                config=["tsconfig.json"],
            ),
        )
        assert cfg.tree_sitter is not None
        assert cfg.tree_sitter.wasm_package == "tree-sitter-typescript"

    def test_missing_id_raises_error(self) -> None:
        """id is required."""
        with pytest.raises(ValidationError):
            LanguageConfig(
                display_name="Python",
                extensions=[".py"],
                concepts=["decorators"],
                file_patterns=FilePatternConfig(),
            )

    def test_missing_display_name_raises_error(self) -> None:
        """displayName is required."""
        with pytest.raises(ValidationError):
            LanguageConfig(
                id="python",
                extensions=[".py"],
                concepts=["decorators"],
                file_patterns=FilePatternConfig(),
            )

    def test_missing_extensions_raises_error(self) -> None:
        """extensions is required."""
        with pytest.raises(ValidationError):
            LanguageConfig(
                id="python",
                display_name="Python",
                concepts=["decorators"],
                file_patterns=FilePatternConfig(),
            )

    def test_empty_id_raises_error(self) -> None:
        """id must be non-empty."""
        with pytest.raises(ValidationError):
            LanguageConfig(
                id="",
                display_name="Python",
                extensions=[".py"],
                concepts=["decorators"],
                file_patterns=FilePatternConfig(),
            )

    def test_empty_display_name_raises_error(self) -> None:
        """displayName must be non-empty."""
        with pytest.raises(ValidationError):
            LanguageConfig(
                id="python",
                display_name="",
                extensions=[".py"],
                concepts=["decorators"],
                file_patterns=FilePatternConfig(),
            )

    def test_camel_case_inputs(self) -> None:
        """All fields accept camelCase aliases."""
        cfg = LanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py"],
            concepts=["decorators"],
            filePatterns={
                "entryPoints": ["main.py"],
                "barrels": ["__init__.py"],
                "tests": [],
                "config": [],
            },
        )
        assert cfg.display_name == "Python"
        assert cfg.file_patterns.entry_points == ["main.py"]
        assert cfg.file_patterns.barrels == ["__init__.py"]

    def test_filenames_optional_with_none_default(self) -> None:
        """filenames defaults to None when not provided."""
        cfg = LanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            concepts=["layers"],
            filePatterns={
                "entryPoints": ["Dockerfile"],
            },
        )
        assert cfg.filenames is None

    def test_tree_sitter_optional(self) -> None:
        """treeSitter is optional — non-code languages don't need it."""
        cfg = LanguageConfig(
            id="markdown",
            displayName="Markdown",
            extensions=[".md"],
            concepts=["headings"],
            filePatterns=FilePatternConfig(),
        )
        assert cfg.tree_sitter is None

    def test_dockerfile_filename_based_config(self) -> None:
        """Filename-only detection: extensions empty, filenames populated."""
        cfg = LanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            filenames=["Dockerfile", "Dockerfile.dev"],
            concepts=["multi-stage builds"],
            filePatterns=FilePatternConfig(entry_points=["Dockerfile"]),
        )
        assert cfg.extensions == []
        assert cfg.filenames == ["Dockerfile", "Dockerfile.dev"]


class TestStrictLanguageConfig:
    """Tests for StrictLanguageConfig (requires extensions or filenames)."""

    def test_extension_only_passes(self) -> None:
        """Config with extensions but no filenames is valid."""
        cfg = StrictLanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py"],
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        )
        assert cfg.id == "python"

    def test_filenames_only_passes(self) -> None:
        """Config with filenames but no extensions is valid."""
        cfg = StrictLanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            filenames=["Dockerfile"],
            concepts=["layers"],
            filePatterns=FilePatternConfig(),
        )
        assert cfg.id == "dockerfile"

    def test_neither_extension_nor_filename_fails(self) -> None:
        """Config with no extensions and no filenames is invalid."""
        with pytest.raises(ValidationError):
            StrictLanguageConfig(
                id="kubernetes",
                displayName="Kubernetes",
                extensions=[],
                concepts=["pods"],
                filePatterns=FilePatternConfig(),
            )

    def test_both_extension_and_filenames_passes(self) -> None:
        """Config with both extensions and filenames is valid."""
        cfg = StrictLanguageConfig(
            id="makefile",
            displayName="Makefile",
            extensions=[".mk"],
            filenames=["Makefile"],
            concepts=["targets"],
            filePatterns=FilePatternConfig(),
        )
        assert cfg.id == "makefile"


class TestFrameworkConfig:
    """Tests for FrameworkConfig model."""

    def test_valid_framework_config(self) -> None:
        cfg = FrameworkConfig(
            id="django",
            display_name="Django",
            languages=["python"],
            detection_keywords=["django", "djangorestframework"],
            manifest_files=["requirements.txt", "pyproject.toml"],
            prompt_snippet_path="./frameworks/django.md",
            entry_points=["manage.py"],
            layer_hints={"views": "api", "models": "data"},
        )
        assert cfg.id == "django"
        assert cfg.languages == ["python"]
        assert cfg.detection_keywords == ["django", "djangorestframework"]

    def test_camel_case_input(self) -> None:
        cfg = FrameworkConfig(
            id="react",
            displayName="React",
            languages=["typescript", "javascript"],
            detectionKeywords=["react", "react-dom"],
            manifestFiles=["package.json"],
            promptSnippetPath="./frameworks/react.md",
            entryPoints=["src/App.tsx"],
            layerHints={"components": "ui"},
        )
        assert cfg.display_name == "React"
        assert cfg.detection_keywords == ["react", "react-dom"]
        assert cfg.manifest_files == ["package.json"]
        assert cfg.prompt_snippet_path == "./frameworks/react.md"
        assert cfg.entry_points == ["src/App.tsx"]
        assert cfg.layer_hints == {"components": "ui"}

    def test_missing_id_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                display_name="Django",
                languages=["python"],
                detection_keywords=["django"],
                manifest_files=["requirements.txt"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_missing_languages_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                detection_keywords=["django"],
                manifest_files=["requirements.txt"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_empty_languages_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                languages=[],
                detection_keywords=["django"],
                manifest_files=["requirements.txt"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_missing_detection_keywords_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                languages=["python"],
                manifest_files=["requirements.txt"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_empty_detection_keywords_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                languages=["python"],
                detection_keywords=[],
                manifest_files=["requirements.txt"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_missing_manifest_files_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                languages=["python"],
                detection_keywords=["django"],
                prompt_snippet_path="./frameworks/django.md",
            )

    def test_missing_prompt_snippet_path_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                display_name="Django",
                languages=["python"],
                detection_keywords=["django"],
                manifest_files=["requirements.txt"],
            )

    def test_entry_points_and_layer_hints_optional(self) -> None:
        """entryPoints and layerHints are optional."""
        cfg = FrameworkConfig(
            id="minimal",
            displayName="Minimal",
            languages=["python"],
            detectionKeywords=["test"],
            manifestFiles=["test.txt"],
            promptSnippetPath="./test.md",
        )
        assert cfg.entry_points is None
        assert cfg.layer_hints is None

    def test_empty_id_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="",
                displayName="Django",
                languages=["python"],
                detectionKeywords=["django"],
                manifestFiles=["requirements.txt"],
                promptSnippetPath="./django.md",
            )

    def test_empty_language_items_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FrameworkConfig(
                id="django",
                displayName="Django",
                languages=[""],
                detectionKeywords=["django"],
                manifestFiles=["requirements.txt"],
                promptSnippetPath="./django.md",
            )
