import configparser

import pytest

from pretalx.common.settings.config import (
    CONFIG,
    build_config,
    read_config_files,
    read_layer,
    reduce_dict,
)

pytestmark = pytest.mark.unit


def test_reduce_dict_removes_none_values():
    data = {"section": {"keep": "value", "drop": None, "also_keep": ""}}

    result = reduce_dict(data)

    assert result == {"section": {"keep": "value", "also_keep": ""}}


def test_reduce_dict_preserves_all_sections():
    data = {"a": {"x": None}, "b": {"y": "keep"}}

    result = reduce_dict(data)

    assert set(result.keys()) == {"a", "b"}
    assert result["a"] == {}
    assert result["b"] == {"y": "keep"}


def test_reduce_dict_empty_input():
    assert reduce_dict({}) == {}


@pytest.mark.parametrize(
    ("section", "key", "expected"),
    (
        ("site", "url", "http://localhost"),
        ("mail", "from", "admin@localhost"),
        ("mail", "host", "localhost"),
        ("mail", "port", "25"),
        ("database", "backend", "sqlite3"),
    ),
)
def test_read_layer_default_values(section, key, expected):
    config = configparser.RawConfigParser()

    config = read_layer("default", config)

    assert config.get(section, key) == expected


def test_read_layer_env_overrides_defaults(monkeypatch):
    """Environment layer values override previous layers."""
    monkeypatch.setitem(CONFIG["site"]["url"], "env", "https://example.com")
    config = configparser.RawConfigParser()
    config = read_layer("default", config)

    config = read_layer("env", config)

    assert config.get("site", "url") == "https://example.com"


def test_read_config_files_without_env_var(monkeypatch, tmp_path):
    """Without PRETALX_CONFIG_FILE, read_config_files reads from default paths."""
    monkeypatch.delenv("PRETALX_CONFIG_FILE", raising=False)
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert isinstance(config_files, list)


def test_read_config_files_with_env_var(monkeypatch, tmp_path):
    """With PRETALX_CONFIG_FILE set, that file is read."""
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("[site]\nurl = https://custom.example.com\n")
    monkeypatch.setenv("PRETALX_CONFIG_FILE", str(cfg_file))
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert config.get("site", "url") == "https://custom.example.com"


def test_build_config_returns_config_and_files():
    config, config_files = build_config()

    assert isinstance(config, configparser.RawConfigParser)
    assert isinstance(config_files, list)


def test_build_config_has_expected_sections():
    config, _ = build_config()

    for section in CONFIG:
        assert config.has_section(section), f"Missing section: {section}"


def test_build_config_env_layer_applied_last(monkeypatch):
    """The env layer is applied after config files, so env vars take precedence."""
    monkeypatch.setitem(CONFIG["mail"]["host"], "env", "smtp.override.example.com")

    config, _ = build_config()

    assert config.get("mail", "host") == "smtp.override.example.com"


def test_config_dict_structure():
    """CONFIG dict has the expected top-level sections."""
    expected_sections = {
        "filesystem",
        "site",
        "database",
        "mail",
        "redis",
        "celery",
        "logging",
        "locale",
        "files",
    }

    assert set(CONFIG.keys()) == expected_sections


def test_config_entries_have_default_or_env():
    """Every config entry has at least a 'default' or 'env' key."""
    for section_name, section in CONFIG.items():
        for key, value in section.items():
            assert "default" in value or "env" in value, (
                f"CONFIG[{section_name!r}][{key!r}] has neither 'default' nor 'env'"
            )
