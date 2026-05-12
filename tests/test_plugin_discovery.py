"""Tests for plugin discovery — config parsing and serialization."""

from __future__ import annotations

import json

from understand_anything.plugins.discovery import (
    DEFAULT_PLUGIN_CONFIG,
    PluginConfig,
    PluginEntry,
    parse_plugin_config,
    serialize_plugin_config,
)


class TestPluginEntry:
    """Tests for PluginEntry dataclass."""

    def test_default_enabled_is_true(self) -> None:
        entry = PluginEntry(name="test", languages=["python"])
        assert entry.enabled is True
        assert entry.options is None

    def test_full_entry(self) -> None:
        entry = PluginEntry(
            name="custom",
            enabled=False,
            languages=["python", "typescript"],
            options={"key": "value"},
        )
        assert entry.name == "custom"
        assert entry.enabled is False
        assert entry.languages == ["python", "typescript"]
        assert entry.options == {"key": "value"}


class TestPluginConfig:
    """Tests for PluginConfig dataclass."""

    def test_empty_plugins(self) -> None:
        cfg = PluginConfig(plugins=[])
        assert cfg.plugins == []

    def test_with_entries(self) -> None:
        entry = PluginEntry(name="tree-sitter", languages=["python"])
        cfg = PluginConfig(plugins=[entry])
        assert len(cfg.plugins) == 1
        assert cfg.plugins[0].name == "tree-sitter"


class TestDefaultPluginConfig:
    """Tests for DEFAULT_PLUGIN_CONFIG."""

    def test_default_config_has_tree_sitter_plugin(self) -> None:
        assert len(DEFAULT_PLUGIN_CONFIG.plugins) == 1
        ts = DEFAULT_PLUGIN_CONFIG.plugins[0]
        assert ts.name == "tree-sitter"
        assert ts.enabled is True
        assert len(ts.languages) > 0

    def test_default_config_includes_code_languages(self) -> None:
        """The default tree-sitter plugin covers all languages with tree-sitter grammars."""
        ts = DEFAULT_PLUGIN_CONFIG.plugins[0]
        # All code languages with tree-sitter support should be included
        assert "python" in ts.languages
        assert "typescript" in ts.languages
        assert "javascript" in ts.languages
        assert "go" in ts.languages
        assert "rust" in ts.languages
        assert "java" in ts.languages

    def test_default_config_excludes_non_code_languages(self) -> None:
        """Non-code languages without tree-sitter grammars should not be in default."""
        ts = DEFAULT_PLUGIN_CONFIG.plugins[0]
        assert "markdown" not in ts.languages
        assert "yaml" not in ts.languages
        assert "json" not in ts.languages
        assert "dockerfile" not in ts.languages


class TestParsePluginConfig:
    """Tests for parse_plugin_config()."""

    def test_parse_valid_json(self) -> None:
        json_str = json.dumps({
            "plugins": [
                {"name": "tree-sitter", "enabled": True, "languages": ["python", "typescript"]},
                {"name": "custom-parser", "enabled": False, "languages": ["markdown"]},
            ],
        })
        cfg = parse_plugin_config(json_str)
        assert len(cfg.plugins) == 2
        assert cfg.plugins[0].name == "tree-sitter"
        assert cfg.plugins[0].enabled is True
        assert cfg.plugins[1].name == "custom-parser"
        assert cfg.plugins[1].enabled is False

    def test_parse_empty_string_returns_default(self) -> None:
        cfg = parse_plugin_config("")
        assert len(cfg.plugins) == 1
        assert cfg.plugins[0].name == "tree-sitter"

    def test_parse_whitespace_string_returns_default(self) -> None:
        cfg = parse_plugin_config("   \n  ")
        assert len(cfg.plugins) == 1
        assert cfg.plugins[0].name == "tree-sitter"

    def test_parse_invalid_json_returns_default(self) -> None:
        cfg = parse_plugin_config("{not valid json")
        assert len(cfg.plugins) == 1
        assert cfg.plugins[0].name == "tree-sitter"

    def test_parse_missing_plugins_key_returns_default(self) -> None:
        cfg = parse_plugin_config('{"something": "else"}')
        assert len(cfg.plugins) == 1

    def test_parse_plugins_not_array_returns_default(self) -> None:
        cfg = parse_plugin_config('{"plugins": "not-an-array"}')
        assert len(cfg.plugins) == 1

    def test_parse_null_plugins_returns_default(self) -> None:
        cfg = parse_plugin_config('{"plugins": null}')
        assert len(cfg.plugins) == 1

    def test_filter_invalid_entries(self) -> None:
        """Entries without name or with empty languages are filtered out."""
        json_str = json.dumps({
            "plugins": [
                {"name": "valid", "languages": ["python"]},
                {},  # no name
                {"name": "no-languages", "languages": []},  # empty languages
                {"languages": ["python"]},  # missing name
                {"name": "", "languages": ["python"]},  # empty name
            ],
        })
        cfg = parse_plugin_config(json_str)
        assert len(cfg.plugins) == 1
        assert cfg.plugins[0].name == "valid"

    def test_enabled_defaults_to_true(self) -> None:
        """Entries without 'enabled' field default to true."""
        json_str = json.dumps({
            "plugins": [
                {"name": "test", "languages": ["python"]},
            ],
        })
        cfg = parse_plugin_config(json_str)
        assert cfg.plugins[0].enabled is True

    def test_preserves_options(self) -> None:
        json_str = json.dumps({
            "plugins": [
                {
                    "name": "tree-sitter",
                    "languages": ["python"],
                    "options": {"maxFileSize": 1048576, "cacheResults": True},
                },
            ],
        })
        cfg = parse_plugin_config(json_str)
        assert cfg.plugins[0].options == {
            "maxFileSize": 1048576,
            "cacheResults": True,
        }

    def test_parse_returns_fresh_default_copy(self) -> None:
        """Each parse returning default should return a new copy, not the same object."""
        cfg1 = parse_plugin_config("invalid")
        cfg2 = parse_plugin_config("invalid")
        assert cfg1 is not cfg2
        # Mutating one shouldn't affect the other
        cfg1.plugins.append(PluginEntry(name="extra", languages=["x"]))
        assert len(cfg2.plugins) == 1


class TestSerializePluginConfig:
    """Tests for serialize_plugin_config()."""

    def test_roundtrip(self) -> None:
        original = PluginConfig(plugins=[
            PluginEntry(
                name="tree-sitter",
                enabled=True,
                languages=["python", "typescript"],
                options={"maxFileSize": 1048576},
            ),
            PluginEntry(
                name="custom",
                enabled=False,
                languages=["markdown"],
            ),
        ])
        json_str = serialize_plugin_config(original)
        parsed = parse_plugin_config(json_str)

        assert len(parsed.plugins) == 2
        assert parsed.plugins[0].name == "tree-sitter"
        assert parsed.plugins[0].enabled is True
        assert parsed.plugins[0].languages == ["python", "typescript"]
        assert parsed.plugins[0].options == {"maxFileSize": 1048576}
        assert parsed.plugins[1].name == "custom"
        assert parsed.plugins[1].enabled is False

    def test_serialize_produces_valid_json(self) -> None:
        cfg = PluginConfig(plugins=[
            PluginEntry(name="test", languages=["python"]),
        ])
        json_str = serialize_plugin_config(cfg)
        # Should be parseable by json.loads
        parsed = json.loads(json_str)
        assert "plugins" in parsed
        assert isinstance(parsed["plugins"], list)

    def test_serialize_is_formatted(self) -> None:
        """Output should be formatted with indent=2."""
        cfg = PluginConfig(plugins=[
            PluginEntry(name="test", languages=["python"]),
        ])
        json_str = serialize_plugin_config(cfg)
        assert "\n" in json_str
        assert "  " in json_str
