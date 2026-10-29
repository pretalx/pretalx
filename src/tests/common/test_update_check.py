# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
import urllib3
from django.core import mail as djmail
from django.db import DatabaseError, connection
from django.utils.timezone import now

from pretalx import __version__
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.update_check import (
    check_result_table,
    get_database_info,
    run_update_check,
    send_update_notification_email,
    update_check,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


UPDATE_CHECK_URL = "https://pretalx.com/.update_check/"


def _stub_response(status=200, json_data=None):
    return SimpleNamespace(status=status, json=lambda: json_data or {})


def _ok_response(updatable, plugins=None):
    return _stub_response(
        status=200,
        json_data={
            "status": "ok",
            "version": {
                "latest": "1000.0.0" if updatable else "1.0.0",
                "yours": __version__,
                "updatable": updatable,
            },
            "plugins": plugins or {},
        },
    )


@pytest.fixture
def patch_urllib3():
    """Patch ``urllib3.request`` and return the ``MagicMock``.

    Each test configures ``return_value`` / ``side_effect`` directly on the
    mock — that's the urllib3 equivalent of the old ``responses.add`` /
    ``responses.add_callback`` calls. ``mock.call_args`` replaces
    ``responses.calls`` for payload inspection."""
    with mock.patch("pretalx.common.update_check.urllib3.request") as patched:
        # Sensible default: return a 200 with an empty body. Tests that care
        # about the response shape override this.
        patched.return_value = _stub_response(status=200, json_data={})
        yield patched


def test_update_check_disabled(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_enabled = False

    run_update_check(None)
    update_check.apply(throw=True)

    assert patch_urllib3.call_count == 0
    assert gs.settings.update_check_last is None


@pytest.mark.parametrize(
    ("hours_ago", "should_trigger"),
    ((None, True), (14, False), (24, True)),
    ids=["never_checked", "recent", "stale"],
)
def test_run_update_check_respects_interval(patch_urllib3, hours_ago, should_trigger):
    gs = GlobalSettings()
    if hours_ago is not None:
        gs.settings.update_check_last = now() - timedelta(hours=hours_ago)

    patch_urllib3.return_value = _ok_response(updatable=False)
    run_update_check(None)

    assert patch_urllib3.call_count == (1 if should_trigger else 0)


def test_update_check_dev_server(monkeypatch, patch_urllib3):
    monkeypatch.setattr(sys, "argv", ["manage.py", "runserver"])

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result == {"error": "development"}
    assert gs.settings.update_check_last is not None
    assert patch_urllib3.call_count == 0


@pytest.mark.parametrize(
    "updatable", (False, True), ids=["no_update", "update_available"]
)
def test_update_check_stores_result(patch_urllib3, updatable):
    patch_urllib3.return_value = _ok_response(updatable=updatable)

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result_warning == updatable
    assert gs.settings.update_check_result["version"]["updatable"] is updatable
    assert gs.settings.update_check_last is not None


@pytest.mark.parametrize(
    ("side_effect", "return_value", "expected_error"),
    (
        (urllib3.exceptions.HTTPError("network down"), None, "unavailable"),
        (None, _stub_response(status=500), "http_error"),
    ),
    ids=["network_error", "http_error"],
)
def test_update_check_error_stores_result(
    patch_urllib3, side_effect, return_value, expected_error
):
    if side_effect is not None:
        patch_urllib3.side_effect = side_effect
    else:
        patch_urllib3.return_value = return_value

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result == {"error": expected_error}
    assert gs.settings.update_check_last is not None


def test_update_check_sends_email_only_on_changed_result(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    patch_urllib3.return_value = _ok_response(updatable=True)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()

    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    patch_urllib3.return_value = _ok_response(updatable=False)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    patch_urllib3.return_value = _ok_response(updatable=True)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 2


def test_update_check_sends_payload(patch_urllib3):
    patch_urllib3.return_value = _ok_response(updatable=False)

    update_check.apply(throw=True)

    assert patch_urllib3.call_count == 1
    call = patch_urllib3.call_args
    assert call.args == ("POST", UPDATE_CHECK_URL)
    payload = call.kwargs["json"]
    assert payload["version"] == __version__
    assert payload["events"] == {"total": 0, "public": 0}
    assert payload["plugins"] == [
        {"name": "tests.dummy_app", "version": "0.0.0"},
        {"name": "tests.dummy_app_no_hooks", "version": "0.0.0"},
    ]
    assert len(payload["id"]) == 32
    assert payload["id"] == GlobalSettings().settings.update_check_id
    assert re.fullmatch(r"\d+\.\d+\.\d+", payload["python_version"])
    assert payload["database"] == get_database_info()
    assert payload["database"]["type"] == connection.vendor
    assert payload["database"]["version"] != "unknown"
    assert re.fullmatch(r"[^.]+(\.[^.]+)*", payload["database"]["version"])


@pytest.mark.parametrize(
    ("vendor", "db_version", "expected"),
    (
        ("postgresql", (15, 3), {"type": "postgresql", "version": "15.3"}),
        ("mysql", (8, 0, 35), {"type": "mysql", "version": "8.0.35"}),
        ("sqlite", (3, 45, 1), {"type": "sqlite", "version": "3.45.1"}),
        ("oracle", (19, 0), {"type": "oracle", "version": "19.0"}),
    ),
    ids=["postgresql", "mysql", "sqlite", "oracle"],
)
def test_get_database_info(vendor, db_version, expected):
    fake = mock.MagicMock()
    fake.vendor = vendor
    fake.get_database_version.return_value = db_version
    with mock.patch("pretalx.common.update_check.connection", fake):
        assert get_database_info() == expected


def test_get_database_info_version_failure():
    fake = mock.MagicMock()
    fake.vendor = "postgresql"
    fake.get_database_version.side_effect = DatabaseError("boom")
    with mock.patch("pretalx.common.update_check.connection", fake):
        assert get_database_info() == {"type": "postgresql", "version": "unknown"}

    fake.get_database_version.side_effect = IndexError("unexpected")
    with mock.patch("pretalx.common.update_check.connection", fake):
        assert get_database_info() == {"type": "postgresql", "version": "unknown"}


def test_send_update_notification_email_requires_configured_address():
    gs = GlobalSettings()
    djmail.outbox = []

    gs.settings.update_check_email = ""
    send_update_notification_email()
    assert len(djmail.outbox) == 0

    gs.settings.update_check_email = "admin@example.com"
    send_update_notification_email()
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()


def test_check_result_table_passes_errors_through():
    gs = GlobalSettings()

    assert check_result_table() == {"error": "no_result"}

    gs.settings.update_check_result = {"error": "unavailable"}
    assert check_result_table() == {"error": "unavailable"}


@pytest.mark.parametrize(
    ("plugins", "updatable", "plugin_latest", "plugin_updatable"),
    (
        ({}, False, None, False),
        (
            {"tests.dummy_app": {"latest": "1.1.1", "updatable": True}},
            True,
            "1.1.1",
            True,
        ),
    ),
    ids=["no_updates", "plugin_update"],
)
def test_check_result_table(
    patch_urllib3, plugins, updatable, plugin_latest, plugin_updatable
):
    patch_urllib3.return_value = _stub_response(
        status=200,
        json_data={
            "status": "ok",
            "version": {
                "latest": "1.0.0",
                "yours": __version__,
                "updatable": updatable,
            },
            "plugins": plugins,
        },
    )
    update_check.apply(throw=True)

    assert check_result_table() == [
        {
            "name": "pretalx",
            "installed": __version__,
            "latest": "1.0.0",
            "updatable": updatable,
        },
        {
            "name": "Plugin: Test Dummy Plugin",
            "installed": "0.0.0",
            "latest": plugin_latest,
            "updatable": plugin_updatable,
        },
        {
            "name": "Plugin: Test Dummy Plugin (No Hooks)",
            "installed": "0.0.0",
            "latest": None,
            "updatable": False,
        },
    ]
