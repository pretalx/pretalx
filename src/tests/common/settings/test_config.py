# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import configparser

import pytest

from pretalx.common.settings import config as config_module
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


def test_read_config_files_reads_source_tree_and_home_not_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("PRETALX_CONFIG_FILE", raising=False)
    monkeypatch.delenv("PRETALX_SKIP_DEFAULT_CONFIG_FILES", raising=False)
    src_dir = tmp_path / "src"
    src_cfg = src_dir / "pretalx.cfg"
    src_dir.mkdir()
    src_cfg.write_text("[site]\nurl = https://src.example.com\n")
    monkeypatch.setattr(
        config_module, "__file__", str(src_dir / "pretalx/common/settings/config.py")
    )
    home_dir = tmp_path / "home"
    home_cfg = home_dir / ".pretalx.cfg"
    home_dir.mkdir()
    home_cfg.write_text("[mail]\nhost = home.example.com\n")
    monkeypatch.setattr(config_module.Path, "home", lambda: home_dir)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "pretalx.cfg").write_text("[mail]\nfrom = cwd@example.com\n")
    monkeypatch.chdir(cwd)
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert config.get("site", "url") == "https://src.example.com"
    assert config.get("mail", "host") == "home.example.com"
    assert not config.has_option("mail", "from")
    assert config_files[-2:] == [home_cfg, src_cfg]


def test_read_config_files_skip_flag_ignores_default_files(monkeypatch, tmp_path):
    monkeypatch.delenv("PRETALX_CONFIG_FILE", raising=False)
    monkeypatch.setenv("PRETALX_SKIP_DEFAULT_CONFIG_FILES", "1")
    (tmp_path / ".pretalx.cfg").write_text("[mail]\nhost = home.example.com\n")
    monkeypatch.setattr(config_module.Path, "home", lambda: tmp_path)
    config = configparser.RawConfigParser()

    config, config_files = read_config_files(config)

    assert config_files == []
    assert not config.has_section("mail")


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
