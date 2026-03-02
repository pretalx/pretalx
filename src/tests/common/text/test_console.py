# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import logging

import pytest
from django.test import override_settings

from pretalx.common.text.console import (
    end_box,
    get_separator,
    log_initial,
    print_line,
    start_box,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("args", "expected"),
    (
        ((True, False, False, False), "└"),
        ((False, True, False, False), "┌"),
        ((False, False, True, False), "┐"),
        ((False, False, False, True), "┘"),
        ((False, True, True, False), "┬"),
        ((True, False, False, True), "┴"),
        ((False, False, True, True), "┤"),
        ((True, True, False, False), "├"),
        ((False, True, False, True), "┼"),
        ((True, False, True, False), "┼"),
        ((True, True, True, False), "┼"),
        ((True, True, False, True), "┼"),
        ((True, False, True, True), "┼"),
        ((False, True, True, True), "┼"),
        ((True, True, True, True), "┼"),
    ),
)
def test_get_separator(args, expected):
    assert get_separator(*args) == expected


def test_start_box(caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        start_box(10)

    assert "━" * 10 in caplog.text


def test_end_box(caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        end_box(10)

    assert "━" * 10 in caplog.text


@pytest.mark.parametrize(
    ("text", "kwargs", "expected"),
    (
        ("Hello", {}, "Hello"),
        ("Test", {"box": True}, "┃ Test ┃"),
        ("Hi", {"box": True, "size": 20}, "┃ Hi" + " " * 16 + " ┃"),
        ("Bold", {"bold": True}, "\033[1mBold\033[0m"),
        ("Red", {"color": "\033[1;31m"}, "\033[1;31mRed\033[0m"),
    ),
)
def test_print_line_formats_output(text, kwargs, expected, caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        print_line(text, **kwargs)

    assert expected in caplog.records[-1].getMessage()


def test_log_initial_skips_without_config_files(settings, caplog):
    settings.CONFIG_FILES = None

    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        log_initial()

    assert "pretalx v" not in caplog.text


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@override_settings(
    CONFIG_FILES=["/etc/pretalx/pretalx.cfg"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    LOG_DIR="/var/log/pretalx",
    PLUGINS=[],
    DEBUG=False,
)
def test_log_initial_with_config(caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        log_initial()

    assert "pretalx v" in caplog.text
    assert "pretalx.cfg" in caplog.text
    assert "sqlite3" in caplog.text


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@override_settings(
    CONFIG_FILES=["/etc/pretalx/pretalx.cfg"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    LOG_DIR="/var/log/pretalx",
    PLUGINS=["pretalx_pages", "pretalx_vimeo"],
    DEBUG=False,
)
def test_log_initial_with_plugins(caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        log_initial()

    assert "Plugins:" in caplog.text
    assert "pretalx_pages" in caplog.text


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@override_settings(
    CONFIG_FILES=["/etc/pretalx/pretalx.cfg"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    LOG_DIR="/var/log/pretalx",
    PLUGINS=[],
    DEBUG=True,
)
def test_log_initial_with_debug(caplog):
    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        log_initial()

    assert "DEVELOPMENT MODE" in caplog.text


def test_log_initial_root_warning(settings, caplog, monkeypatch):
    settings.CONFIG_FILES = None
    monkeypatch.setattr("os.geteuid", lambda: 0)

    with caplog.at_level(logging.INFO, logger="pretalx.common.text.console"):
        log_initial()

    assert "root" in caplog.text
