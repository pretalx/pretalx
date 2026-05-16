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
    """Build an object shaped like a ``urllib3.HTTPResponse``.

    Only the bits the update-check code actually touches (``status`` and
    ``json()``) — keeps the test stub minimal and obvious."""
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


def test_run_update_check_disabled(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_enabled = False

    run_update_check(None)

    assert patch_urllib3.call_count == 0


@pytest.mark.parametrize(
    ("hours_ago", "should_trigger"),
    ((None, True), (14, False), (24, True)),
    ids=["never_checked", "recent", "stale"],
)
def test_run_update_check_respects_interval(patch_urllib3, hours_ago, should_trigger):
    """Triggers a new check when no previous check exists or the last check is
    older than 23 hours; skips when it was more recent."""
    gs = GlobalSettings()
    if hours_ago is not None:
        gs.settings.update_check_last = now() - timedelta(hours=hours_ago)

    patch_urllib3.return_value = _ok_response(updatable=False)
    run_update_check(None)

    assert patch_urllib3.call_count == (1 if should_trigger else 0)


def test_update_check_disabled(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_enabled = False

    update_check.apply(throw=True)

    assert patch_urllib3.call_count == 0


def test_update_check_sets_id_on_first_run(patch_urllib3):
    patch_urllib3.return_value = _ok_response(updatable=False)
    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_id is not None
    assert len(gs.settings.update_check_id) == 32  # hex uuid4


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


def test_update_check_sends_email(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    patch_urllib3.return_value = _ok_response(updatable=True)
    update_check.apply(throw=True)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()


def test_update_check_no_email_on_same_result(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    patch_urllib3.return_value = _ok_response(updatable=True)

    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1


def test_update_check_sends_email_on_changed_result(patch_urllib3):
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    patch_urllib3.return_value = _ok_response(updatable=True)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    patch_urllib3.return_value = _ok_response(updatable=False)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    patch_urllib3.return_value = _ok_response(updatable=True)
    update_check.apply(throw=True)
    assert len(djmail.outbox) == 2


def test_update_check_sends_payload(patch_urllib3):
    """Verify the payload sent to the update server contains the expected
    fields: id, version, events, and plugins."""
    patch_urllib3.return_value = _ok_response(updatable=False)

    update_check.apply(throw=True)

    assert patch_urllib3.call_count == 1
    call = patch_urllib3.call_args
    assert call.args == ("POST", UPDATE_CHECK_URL)
    payload = call.kwargs["json"]
    assert payload["version"] == __version__
    assert payload["events"] == {"total": 0, "public": 0}
    assert {"name": "tests.dummy_app", "version": "0.0.0"} in payload["plugins"]
    assert all("name" in p and "version" in p for p in payload["plugins"])
    assert len(payload["id"]) == 32
    assert re.fullmatch(r"\d+\.\d+\.\d+", payload["python_version"])
    assert set(payload["database"]) == {"type", "version"}
    assert payload["database"]["type"] == connection.vendor
    assert re.fullmatch(r"[^.]+(\.[^.]+)*", payload["database"]["version"])


def test_get_database_info_real_connection():
    info = get_database_info()
    assert info["type"] == connection.vendor
    assert info["version"] != "unknown"
    # The production code uses str(part), so version segments are not
    # guaranteed numeric; only assert the dotted structure is populated.
    assert all(part for part in info["version"].split("."))


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


def test_send_update_notification_email_no_email_configured():
    gs = GlobalSettings()
    gs.settings.update_check_email = ""
    djmail.outbox = []

    send_update_notification_email()

    assert len(djmail.outbox) == 0


def test_send_update_notification_email_sends():
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    send_update_notification_email()

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()


def test_check_result_table_no_result():
    assert check_result_table() == {"error": "no_result"}


def test_check_result_table_error_result():
    gs = GlobalSettings()
    gs.settings.update_check_result = {"error": "unavailable"}

    assert check_result_table() == {"error": "unavailable"}


def test_check_result_table_no_updates(patch_urllib3):
    patch_urllib3.return_value = _ok_response(updatable=False)
    update_check.apply(throw=True)

    table = check_result_table()

    assert table[0] == ("pretalx", __version__, "1.0.0", False)
    plugin_row = next(r for r in table if "Test Dummy Plugin" in str(r[0]))
    assert plugin_row[1] == "0.0.0"
    assert plugin_row[2] == "?"
    assert plugin_row[3] is False


def test_check_result_table_with_plugin_update(patch_urllib3):
    # Server reports the pretalx version as latest=1.0.0 but updatable=True
    # (contradictory in practice; the helper just shows the table cells the
    # response yields). The plugin is also flagged updatable.
    patch_urllib3.return_value = _stub_response(
        status=200,
        json_data={
            "status": "ok",
            "version": {"latest": "1.0.0", "yours": __version__, "updatable": True},
            "plugins": {"tests.dummy_app": {"latest": "1.1.1", "updatable": True}},
        },
    )
    update_check.apply(throw=True)

    table = check_result_table()

    assert table[0] == ("pretalx", __version__, "1.0.0", True)
    plugin_row = next(r for r in table if "Test Dummy Plugin" in str(r[0]))
    assert plugin_row[1] == "0.0.0"
    assert plugin_row[2] == "1.1.1"
    assert plugin_row[3] is True
