# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
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


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        (
            {"section": {"keep": "value", "drop": None, "also_keep": ""}},
            {"section": {"keep": "value", "also_keep": ""}},
        ),
        ({"a": {"x": None}, "b": {"y": "keep"}}, {"a": {}, "b": {"y": "keep"}}),
        ({}, {}),
    ),
    ids=("drops_none_values", "keeps_emptied_sections", "empty"),
)
def test_reduce_dict(data, expected):
    assert reduce_dict(data) == expected


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
    monkeypatch.setitem(CONFIG["site"]["url"], "env", "https://example.com")
    config = configparser.RawConfigParser()
    config = read_layer("default", config)

    config = read_layer("env", config)

    assert config.get("site", "url") == "https://example.com"


def test_read_config_files_without_env_var(monkeypatch):
    monkeypatch.delenv("PRETALX_CONFIG_FILE", raising=False)
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert isinstance(config_files, list)


def test_read_config_files_with_env_var(monkeypatch, tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("[site]\nurl = https://custom.example.com\n")
    monkeypatch.setenv("PRETALX_CONFIG_FILE", str(cfg_file))
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert config.get("site", "url") == "https://custom.example.com"
    assert config_files == [cfg_file]


def test_build_config_has_all_sections_with_env_layer_applied_last(monkeypatch):
    monkeypatch.setitem(CONFIG["mail"]["host"], "env", "smtp.override.example.com")

    config, _ = build_config()

    for section in CONFIG:
        assert config.has_section(section), f"Missing section: {section}"
    assert config.get("mail", "host") == "smtp.override.example.com"


def test_config_entries_have_default_or_env():
    for section_name, section in CONFIG.items():
        for key, value in section.items():
            assert "default" in value or "env" in value, (
                f"CONFIG[{section_name!r}][{key!r}] has neither 'default' nor 'env'"
            )
