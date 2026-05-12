"""Tests for LanguageRegistry — extension/filename mapping."""

from __future__ import annotations

import pytest

from understand_anything.languages.registry import LanguageRegistry
from understand_anything.languages.types import FilePatternConfig, LanguageConfig


class TestLanguageRegistryRegistration:
    """Tests for LanguageRegistry.register() and lookups."""

    def test_register_single_config(self) -> None:
        registry = LanguageRegistry()
        cfg = LanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py", ".pyi"],
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        )
        registry.register(cfg)

        assert registry.get_by_id("python") is not None
        assert registry.get_by_extension(".py") is not None

    def test_register_populates_by_id(self) -> None:
        registry = LanguageRegistry()
        cfg = LanguageConfig(
            id="go",
            displayName="Go",
            extensions=[".go"],
            concepts=["goroutines"],
            filePatterns=FilePatternConfig(),
        )
        registry.register(cfg)

        result = registry.get_by_id("go")
        assert result is not None
        assert result.id == "go"
        assert result.display_name == "Go"

    def test_get_by_id_returns_none_for_unknown(self) -> None:
        registry = LanguageRegistry()
        assert registry.get_by_id("nonexistent") is None

    def test_get_by_extension_returns_none_for_unknown(self) -> None:
        registry = LanguageRegistry()
        assert registry.get_by_extension(".xyz") is None


class TestLanguageRegistryExtensionMapping:
    """Tests for extension-based file resolution."""

    @pytest.fixture
    def registry_with_python(self) -> LanguageRegistry:
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py", ".pyi"],
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        ))
        return registry

    def test_get_by_extension_exact(self, registry_with_python: LanguageRegistry) -> None:
        result = registry_with_python.get_by_extension(".py")
        assert result is not None
        assert result.id == "python"

    def test_get_by_extension_without_dot(self, registry_with_python: LanguageRegistry) -> None:
        """Extensions without leading dot are normalized automatically."""
        result = registry_with_python.get_by_extension("py")
        assert result is not None
        assert result.id == "python"

    def test_get_by_extension_case_insensitive(self) -> None:
        """Extension lookup is case-insensitive."""
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="typescript",
            displayName="TypeScript",
            extensions=[".ts"],
            concepts=["generics"],
            filePatterns=FilePatternConfig(),
        ))
        assert registry.get_by_extension(".TS") is not None
        assert registry.get_by_extension(".Ts") is not None

    def test_register_normalizes_extension_without_dot(self) -> None:
        """Registering an extension without leading dot still stores it with dot."""
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="python",
            displayName="Python",
            extensions=["py"],  # no leading dot
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        ))
        # Should still resolve with dot
        assert registry.get_by_extension(".py") is not None
        assert registry.get_by_extension("py") is not None


class TestLanguageRegistryFilenameMapping:
    """Tests for filename-based file resolution."""

    @pytest.fixture
    def registry_with_dockerfile(self) -> LanguageRegistry:
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            filenames=["Dockerfile", "Dockerfile.dev"],
            concepts=["layers"],
            filePatterns=FilePatternConfig(),
        ))
        return registry

    def test_get_by_filename_exact(self, registry_with_dockerfile: LanguageRegistry) -> None:
        result = registry_with_dockerfile.get_by_filename("Dockerfile")
        assert result is not None
        assert result.id == "dockerfile"

    def test_get_by_filename_case_insensitive(self, registry_with_dockerfile: LanguageRegistry) -> None:
        """Filename lookup is case-insensitive."""
        result = registry_with_dockerfile.get_by_filename("dockerfile")
        assert result is not None
        assert result.id == "dockerfile"

    def test_get_by_filename_returns_none_for_unknown(self, registry_with_dockerfile: LanguageRegistry) -> None:
        assert registry_with_dockerfile.get_by_filename("UnknownFile") is None


class TestLanguageRegistryGetForFile:
    """Tests for the main get_for_file() resolution method."""

    @pytest.fixture
    def registry(self) -> LanguageRegistry:
        reg = LanguageRegistry()
        # Code language
        reg.register(LanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py"],
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        ))
        # Filename-only
        reg.register(LanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            filenames=["Dockerfile"],
            concepts=["layers"],
            filePatterns=FilePatternConfig(),
        ))
        # Both extension and filename
        reg.register(LanguageConfig(
            id="makefile",
            displayName="Makefile",
            extensions=[".mk"],
            filenames=["Makefile"],
            concepts=["targets"],
            filePatterns=FilePatternConfig(),
        ))
        return reg

    def test_resolves_by_extension(self, registry: LanguageRegistry) -> None:
        result = registry.get_for_file("src/main.py")
        assert result is not None
        assert result.id == "python"

    def test_resolves_by_filename_priority(self, registry: LanguageRegistry) -> None:
        """Filename match takes priority over extension match."""
        result = registry.get_for_file("Dockerfile")
        assert result is not None
        assert result.id == "dockerfile"

    def test_resolves_makefile_by_filename(self, registry: LanguageRegistry) -> None:
        """Makefile with no extension matches by filename."""
        result = registry.get_for_file("path/to/Makefile")
        assert result is not None
        assert result.id == "makefile"

    def test_resolves_makefile_by_extension(self, registry: LanguageRegistry) -> None:
        result = registry.get_for_file("rules.mk")
        assert result is not None
        assert result.id == "makefile"

    def test_resolves_dockerfile_in_subdirectory(self, registry: LanguageRegistry) -> None:
        result = registry.get_for_file("docker/app/Dockerfile")
        assert result is not None
        assert result.id == "dockerfile"

    def test_returns_none_for_unknown_file(self, registry: LanguageRegistry) -> None:
        assert registry.get_for_file("unknown.xyz") is None

    def test_returns_none_for_no_extension_and_no_filename_match(self, registry: LanguageRegistry) -> None:
        assert registry.get_for_file("README") is None

    def test_filename_match_wins_over_extension(self) -> None:
        """Filename match is checked first — more specific."""
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="docker-compose",
            displayName="Docker Compose",
            extensions=[],  # no extension
            filenames=["docker-compose.yml"],
            concepts=["services"],
            filePatterns=FilePatternConfig(),
        ))
        # "docker-compose.yml" has .yml extension but should match by filename first
        result = registry.get_for_file("docker-compose.yml")
        assert result is not None
        assert result.id == "docker-compose"

    def test_get_for_file_case_insensitive_extension(self) -> None:
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="python",
            displayName="Python",
            extensions=[".py"],
            concepts=["decorators"],
            filePatterns=FilePatternConfig(),
        ))
        result = registry.get_for_file("main.PY")
        assert result is not None
        assert result.id == "python"

    def test_get_for_file_case_insensitive_filename(self) -> None:
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="dockerfile",
            displayName="Dockerfile",
            extensions=[],
            filenames=["Dockerfile"],
            concepts=["layers"],
            filePatterns=FilePatternConfig(),
        ))
        result = registry.get_for_file("DOCKERFILE")
        assert result is not None
        assert result.id == "dockerfile"


class TestLanguageRegistryGetAll:
    """Tests for getAllLanguages()."""

    def test_get_all_languages(self) -> None:
        registry = LanguageRegistry()
        registry.register(LanguageConfig(
            id="python", displayName="Python",
            extensions=[".py"], concepts=["a"],
            filePatterns=FilePatternConfig(),
        ))
        registry.register(LanguageConfig(
            id="go", displayName="Go",
            extensions=[".go"], concepts=["b"],
            filePatterns=FilePatternConfig(),
        ))

        all_langs = registry.get_all_languages()
        assert len(all_langs) == 2
        ids = {c.id for c in all_langs}
        assert ids == {"python", "go"}

    def test_get_all_languages_empty(self) -> None:
        registry = LanguageRegistry()
        assert registry.get_all_languages() == []


class TestLanguageRegistryCreateDefault:
    """Tests for createDefault() factory method."""

    def test_create_default_registers_all_builtins(self) -> None:
        registry = LanguageRegistry.create_default()

        # Code languages
        assert registry.get_by_id("python") is not None
        assert registry.get_by_id("typescript") is not None
        assert registry.get_by_id("javascript") is not None
        assert registry.get_by_id("go") is not None
        assert registry.get_by_id("rust") is not None
        assert registry.get_by_id("java") is not None
        assert registry.get_by_id("ruby") is not None
        assert registry.get_by_id("php") is not None
        assert registry.get_by_id("cpp") is not None
        assert registry.get_by_id("c") is not None
        assert registry.get_by_id("csharp") is not None

        # Non-code languages
        assert registry.get_by_id("markdown") is not None
        assert registry.get_by_id("yaml") is not None
        assert registry.get_by_id("json") is not None
        assert registry.get_by_id("toml") is not None
        assert registry.get_by_id("dockerfile") is not None
        assert registry.get_by_id("sql") is not None

    def test_create_default_file_resolution(self) -> None:
        registry = LanguageRegistry.create_default()

        # Extension-based
        assert registry.get_for_file("src/main.py") is not None
        assert registry.get_for_file("src/index.ts") is not None
        assert registry.get_for_file("main.go") is not None
        assert registry.get_for_file("lib.rs") is not None
        assert registry.get_for_file("README.md") is not None
        assert registry.get_for_file("config.yaml") is not None
        assert registry.get_for_file("package.json") is not None
        assert registry.get_for_file("data.sql") is not None
        assert registry.get_for_file("main.tf") is not None

        # Filename-based
        assert registry.get_for_file("Dockerfile") is not None
        assert registry.get_for_file("Makefile") is not None
        assert registry.get_for_file("Jenkinsfile") is not None

    def test_create_default_is_idempotent(self) -> None:
        """Calling create_default() twice produces equivalent registries."""
        r1 = LanguageRegistry.create_default()
        r2 = LanguageRegistry.create_default()
        assert len(r1.get_all_languages()) == len(r2.get_all_languages())
