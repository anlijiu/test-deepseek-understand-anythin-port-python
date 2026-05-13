"""Tests for FrameworkRegistry — framework detection from manifests."""

from __future__ import annotations

import pytest

from understand_anything.languages.framework_registry import FrameworkRegistry
from understand_anything.languages.types import FrameworkConfig


class TestFrameworkRegistryRegistration:
    """Tests for FrameworkRegistry.register() and lookups."""

    def test_register_single_framework(self) -> None:
        registry = FrameworkRegistry()
        cfg = FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django"],
            manifestFiles=["requirements.txt"],
            promptSnippetPath="./django.md",
        )
        registry.register(cfg)

        assert registry.get_by_id("django") is not None
        assert len(registry.get_for_language("python")) == 1

    def test_register_duplicate_is_ignored(self) -> None:
        """Registering the same id twice is silently ignored."""
        registry = FrameworkRegistry()
        cfg = FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django"],
            manifestFiles=["requirements.txt"],
            promptSnippetPath="./django.md",
        )
        registry.register(cfg)
        registry.register(cfg)  # duplicate
        assert len(registry.get_all_frameworks()) == 1

    def test_get_by_id_returns_none_for_unknown(self) -> None:
        registry = FrameworkRegistry()
        assert registry.get_by_id("unknown") is None

    def test_get_for_language_returns_empty_for_unknown(self) -> None:
        registry = FrameworkRegistry()
        assert registry.get_for_language("unknown") == []

    def test_get_for_language_returns_copy(self) -> None:
        """get_for_language returns a copy — mutation safe."""
        registry = FrameworkRegistry()
        registry.register(FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django"],
            manifestFiles=["requirements.txt"],
            promptSnippetPath="./django.md",
        ))
        result = registry.get_for_language("python")
        result.clear()
        # Original should be untouched
        assert len(registry.get_for_language("python")) == 1


class TestFrameworkRegistryMultiLanguage:
    """Tests for frameworks supporting multiple languages."""

    def test_framework_registered_for_all_languages(self) -> None:
        registry = FrameworkRegistry()
        cfg = FrameworkConfig(
            id="react",
            displayName="React",
            languages=["typescript", "javascript"],
            detectionKeywords=["react"],
            manifestFiles=["package.json"],
            promptSnippetPath="./react.md",
        )
        registry.register(cfg)

        assert len(registry.get_for_language("typescript")) == 1
        assert len(registry.get_for_language("javascript")) == 1
        assert registry.get_for_language("typescript")[0].id == "react"
        assert registry.get_for_language("javascript")[0].id == "react"

    def test_multiple_frameworks_for_same_language(self) -> None:
        registry = FrameworkRegistry()
        registry.register(FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django"],
            manifestFiles=["requirements.txt"],
            promptSnippetPath="./django.md",
        ))
        registry.register(FrameworkConfig(
            id="flask",
            displayName="Flask",
            languages=["python"],
            detectionKeywords=["flask"],
            manifestFiles=["requirements.txt"],
            promptSnippetPath="./flask.md",
        ))

        python_frameworks = registry.get_for_language("python")
        assert len(python_frameworks) == 2
        ids = {f.id for f in python_frameworks}
        assert ids == {"django", "flask"}


class TestFrameworkRegistryDetection:
    """Tests for detectFrameworks() — the core detection algorithm."""

    @pytest.fixture
    def registry(self) -> FrameworkRegistry:
        reg = FrameworkRegistry()
        # Django — detects from requirements.txt or pyproject.toml
        reg.register(FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django", "djangorestframework"],
            manifestFiles=["requirements.txt", "pyproject.toml", "setup.py"],
            promptSnippetPath="./django.md",
        ))
        # FastAPI — also from pyproject.toml
        reg.register(FrameworkConfig(
            id="fastapi",
            displayName="FastAPI",
            languages=["python"],
            detectionKeywords=["fastapi", "uvicorn", "starlette"],
            manifestFiles=["requirements.txt", "pyproject.toml"],
            promptSnippetPath="./fastapi.md",
        ))
        # React — from package.json
        reg.register(FrameworkConfig(
            id="react",
            displayName="React",
            languages=["typescript", "javascript"],
            detectionKeywords=["react", "react-dom"],
            manifestFiles=["package.json"],
            promptSnippetPath="./react.md",
        ))
        # Gin — from go.mod
        reg.register(FrameworkConfig(
            id="gin",
            displayName="Gin",
            languages=["go"],
            detectionKeywords=["github.com/gin-gonic/gin"],
            manifestFiles=["go.mod"],
            promptSnippetPath="./gin.md",
        ))
        return reg

    def test_detects_django_from_requirements(self, registry: FrameworkRegistry) -> None:
        manifests = {"requirements.txt": "django==4.2\nrestframework==3.14\n"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "django"

    def test_detects_django_from_pyproject(self, registry: FrameworkRegistry) -> None:
        manifests = {"pyproject.toml": "[project]\ndependencies = [\"django>=4.2\"]\n"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "django"

    def test_detection_is_case_insensitive(self, registry: FrameworkRegistry) -> None:
        manifests = {"requirements.txt": "Django==4.2\n"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "django"

    def test_detects_fastapi(self, registry: FrameworkRegistry) -> None:
        manifests = {"requirements.txt": "fastapi==0.100.0\nuvicorn==0.23.0\n"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "fastapi"

    def test_detects_multiple_frameworks(self, registry: FrameworkRegistry) -> None:
        """A project can use both Django and DRF (same framework) — or Django + React."""
        manifests = {
            "requirements.txt": "django>=4.2\n",
            "package.json": '{"dependencies": {"react": "^18.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert ids == {"django", "react"}

    def test_no_detection_without_matching_keywords(self, registry: FrameworkRegistry) -> None:
        manifests = {"requirements.txt": "requests==2.28\npytest==7.0\n"}
        results = registry.detect_frameworks(manifests)
        assert results == []

    def test_no_detection_without_manifest_files(self, registry: FrameworkRegistry) -> None:
        manifests = {"README.md": "django project"}
        results = registry.detect_frameworks(manifests)
        assert results == []

    def test_detection_via_path_with_slash(self, registry: FrameworkRegistry) -> None:
        """Manifest files can be specified with path prefix like 'subdir/package.json'."""
        manifests = {"frontend/package.json": '{"dependencies": {"react": "^18"}}'}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "react"

    def test_empty_manifests(self, registry: FrameworkRegistry) -> None:
        results = registry.detect_frameworks({})
        assert results == []

    def test_detects_gin_from_go_mod(self, registry: FrameworkRegistry) -> None:
        manifests = {"go.mod": "module myapp\n\nrequire github.com/gin-gonic/gin v1.9.0\n"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "gin"

    def test_does_not_detect_gin_from_unrelated_go_mod(self, registry: FrameworkRegistry) -> None:
        manifests = {"go.mod": "module myapp\n\nrequire github.com/gorilla/mux v1.8.0\n"}
        results = registry.detect_frameworks(manifests)
        assert results == []

    def test_detects_spring_from_pom_xml(self) -> None:
        registry = FrameworkRegistry()
        registry.register(FrameworkConfig(
            id="spring",
            displayName="Spring Boot",
            languages=["java"],
            detectionKeywords=["spring-boot", "spring-boot-starter"],
            manifestFiles=["pom.xml", "build.gradle"],
            promptSnippetPath="./spring.md",
        ))
        manifests = {"pom.xml": "<dependency>\n  <artifactId>spring-boot-starter-web</artifactId>\n</dependency>"}
        results = registry.detect_frameworks(manifests)
        assert len(results) == 1
        assert results[0].id == "spring"


class TestFrameworkRegistryCreateDefault:
    """Tests for createDefault() factory method."""

    def test_create_default_registers_all_builtins(self) -> None:
        registry = FrameworkRegistry.create_default()

        frameworks = registry.get_all_frameworks()
        assert len(frameworks) == 10

        ids = {f.id for f in frameworks}
        assert ids == {
            "django", "fastapi", "flask",
            "react", "nextjs", "express", "vue",
            "spring", "rails", "gin",
        }

    def test_create_default_language_mappings(self) -> None:
        registry = FrameworkRegistry.create_default()

        # Python frameworks
        python_fws = registry.get_for_language("python")
        assert len(python_fws) == 3  # Django, FastAPI, Flask

        # JS/TS frameworks
        js_fws = registry.get_for_language("javascript")
        assert len(js_fws) >= 4  # React, Next.js, Express, Vue

        ts_fws = registry.get_for_language("typescript")
        assert len(ts_fws) >= 4

        # Go framework
        go_fws = registry.get_for_language("go")
        assert len(go_fws) == 1
        assert go_fws[0].id == "gin"

        # Ruby framework
        ruby_fws = registry.get_for_language("ruby")
        assert len(ruby_fws) == 1
        assert ruby_fws[0].id == "rails"

        # Java framework
        java_fws = registry.get_for_language("java")
        assert len(java_fws) == 1
        assert java_fws[0].id == "spring"

    def test_create_default_detection_django(self) -> None:
        registry = FrameworkRegistry.create_default()
        manifests = {"requirements.txt": "django==4.2\ndjangorestframework==3.14\n"}
        results = registry.detect_frameworks(manifests)
        assert any(r.id == "django" for r in results)

    def test_create_default_detection_react(self) -> None:
        registry = FrameworkRegistry.create_default()
        manifests = {"package.json": '{"dependencies": {"react": "^18.0", "react-dom": "^18.0"}}'}
        results = registry.detect_frameworks(manifests)
        assert any(r.id == "react" for r in results)

    def test_create_default_is_idempotent(self) -> None:
        r1 = FrameworkRegistry.create_default()
        r2 = FrameworkRegistry.create_default()
        assert len(r1.get_all_frameworks()) == len(r2.get_all_frameworks())


class TestFrameworkRegistryFalsePositives:
    """Tests that false-positive substring matches are avoided.

    Before structural parsing, bare ``keyword in content`` would match
    ``"preact"`` as ``"react"`` or ``"flask-login"`` as ``"flask"``.
    """

    @pytest.fixture
    def registry(self) -> FrameworkRegistry:
        reg = FrameworkRegistry()
        reg.register(FrameworkConfig(
            id="react",
            displayName="React",
            languages=["javascript"],
            detectionKeywords=["react", "react-dom", "@types/react"],
            manifestFiles=["package.json"],
            promptSnippetPath="./react.md",
        ))
        reg.register(FrameworkConfig(
            id="flask",
            displayName="Flask",
            languages=["python"],
            detectionKeywords=["flask", "flask-restful"],
            manifestFiles=["requirements.txt", "pyproject.toml"],
            promptSnippetPath="./flask.md",
        ))
        reg.register(FrameworkConfig(
            id="nextjs",
            displayName="Next.js",
            languages=["javascript"],
            detectionKeywords=["next", "@next/font"],
            manifestFiles=["package.json"],
            promptSnippetPath="./nextjs.md",
        ))
        reg.register(FrameworkConfig(
            id="vue",
            displayName="Vue",
            languages=["javascript"],
            detectionKeywords=["vue", "@vue/cli-service"],
            manifestFiles=["package.json"],
            promptSnippetPath="./vue.md",
        ))
        return reg

    def test_preact_not_detected_as_react(self, registry: FrameworkRegistry) -> None:
        """preact is a substring of 'react' but should NOT match."""
        manifests = {
            "package.json": '{"dependencies": {"preact": "^10.0.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "react" not in ids

    def test_flask_login_not_detected_as_flask(self, registry: FrameworkRegistry) -> None:
        """flask-login contains 'flask' but should NOT match."""
        manifests = {
            "requirements.txt": "flask-login==0.6.0\n",
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "flask" not in ids

    def test_flask_login_not_detected_as_flask_pyproject(
        self, registry: FrameworkRegistry
    ) -> None:
        """Same false-positive check via pyproject.toml."""
        manifests = {
            "pyproject.toml": (
                '[project]\n'
                'dependencies = ["flask-login>=0.6"]\n'
            ),
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "flask" not in ids

    def test_react_still_detected(self, registry: FrameworkRegistry) -> None:
        """True positive: react IS detected."""
        manifests = {
            "package.json": '{"dependencies": {"react": "^18.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "react" in ids

    def test_flask_still_detected(self, registry: FrameworkRegistry) -> None:
        """True positive: flask IS detected from requirements.txt."""
        manifests = {
            "requirements.txt": "flask==2.3.0\n",
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "flask" in ids

    def test_vue_router_without_vue_not_detected(self, registry: FrameworkRegistry) -> None:
        """vue-router and vuex without 'vue' should NOT detect vue."""
        manifests = {
            "package.json": '{"dependencies": {"vue-router": "^4.0", "vuex": "^4.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "vue" not in ids

    def test_vue_still_detected(self, registry: FrameworkRegistry) -> None:
        """True positive: vue IS detected."""
        manifests = {
            "package.json": '{"dependencies": {"vue": "^3.0", "vue-router": "^4.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "vue" in ids

    def test_next_still_detected(self, registry: FrameworkRegistry) -> None:
        """True positive: next IS detected from package.json structural parse."""
        manifests = {
            "package.json": '{"dependencies": {"next": "^14.0", "react": "^18.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "nextjs" in ids

    def test_next_auth_without_next_not_detected(self, registry: FrameworkRegistry) -> None:
        """next-auth without 'next' should NOT detect Next.js."""
        manifests = {
            "package.json": '{"dependencies": {"next-auth": "^4.0", "react": "^18.0"}}',
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "nextjs" not in ids

    def test_poetry_pyproject_dependencies_are_detected(self) -> None:
        """Poetry stores dependencies under top-level tool.poetry."""
        registry = FrameworkRegistry()
        registry.register(FrameworkConfig(
            id="django",
            displayName="Django",
            languages=["python"],
            detectionKeywords=["django"],
            manifestFiles=["pyproject.toml"],
            promptSnippetPath="./django.md",
        ))

        manifests = {
            "pyproject.toml": (
                "[tool.poetry.dependencies]\n"
                'python = "^3.12"\n'
                'django = "^5.0"\n'
            ),
        }
        results = registry.detect_frameworks(manifests)
        ids = {r.id for r in results}
        assert "django" in ids
