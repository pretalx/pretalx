# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import sys
from datetime import timedelta

import pytest
import requests as _requests
import responses
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx import __version__
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.update_check import (
    check_result_table,
    run_update_check,
    send_update_notification_email,
    update_check,
)

pytestmark = pytest.mark.unit


def _response_updatable(request):
    body = json.loads(request.body.decode())
    return (
        200,
        {},
        json.dumps(
            {
                "status": "ok",
                "version": {
                    "latest": "1000.0.0",
                    "yours": body.get("version"),
                    "updatable": True,
                },
                "plugins": {},
            }
        ),
    )


def _response_not_updatable(request):
    body = json.loads(request.body.decode())
    return (
        200,
        {},
        json.dumps(
            {
                "status": "ok",
                "version": {
                    "latest": "1.0.0",
                    "yours": body.get("version"),
                    "updatable": False,
                },
                "plugins": {},
            }
        ),
    )


def _response_with_plugin(request):
    body = json.loads(request.body.decode())
    return (
        200,
        {},
        json.dumps(
            {
                "status": "ok",
                "version": {
                    "latest": "1.0.0",
                    "yours": body.get("version"),
                    "updatable": True,
                },
                "plugins": {"tests.dummy_app": {"latest": "1.1.1", "updatable": True}},
            }
        ),
    )


UPDATE_CHECK_URL = "https://pretalx.com/.update_check/"


@pytest.mark.django_db
@responses.activate
def test_run_update_check_disabled():
    """When update checks are disabled, the periodic task does nothing."""
    gs = GlobalSettings()
    gs.settings.update_check_enabled = False

    responses.add(
        responses.POST, UPDATE_CHECK_URL, body="should not be called", status=500
    )
    run_update_check(None)

    assert len(responses.calls) == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("hours_ago", "should_trigger"),
    ((None, True), (14, False), (24, True)),
    ids=["never_checked", "recent", "stale"],
)
@responses.activate
def test_run_update_check_respects_interval(hours_ago, should_trigger):
    """Triggers a new check when no previous check exists or the last check is
    older than 23 hours; skips when it was more recent."""
    gs = GlobalSettings()
    if hours_ago is not None:
        gs.settings.update_check_last = now() - timedelta(hours=hours_ago)

    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_not_updatable
    )
    run_update_check(None)
    assert len(responses.calls) == (1 if should_trigger else 0)


@pytest.mark.django_db
@responses.activate
def test_update_check_disabled():
    """When disabled, no HTTP request is made."""
    gs = GlobalSettings()
    gs.settings.update_check_enabled = False

    responses.add(
        responses.POST, UPDATE_CHECK_URL, body="should not be called", status=500
    )
    update_check.apply(throw=True)

    assert len(responses.calls) == 0


@pytest.mark.django_db
@responses.activate
def test_update_check_sets_id_on_first_run():
    """The first run should generate and persist an update_check_id.

    The default for update_check_id is None on a fresh database, so the
    task should generate one on first run."""
    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_not_updatable
    )
    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_id is not None
    assert len(gs.settings.update_check_id) == 32  # hex uuid4


@pytest.mark.django_db
def test_update_check_dev_server(monkeypatch):
    """In development mode (runserver in sys.argv), sets a development error
    result instead of making an HTTP request."""
    monkeypatch.setattr(sys, "argv", ["manage.py", "runserver"])

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result == {"error": "development"}
    assert gs.settings.update_check_last is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("callback", "expected_updatable"),
    ((_response_not_updatable, False), (_response_updatable, True)),
    ids=["no_update", "update_available"],
)
@responses.activate
def test_update_check_stores_result(callback, expected_updatable):
    responses.add_callback(responses.POST, UPDATE_CHECK_URL, callback=callback)

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result_warning == expected_updatable
    assert gs.settings.update_check_result["version"]["updatable"] is expected_updatable
    assert gs.settings.update_check_last is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("response_kwargs", "expected_error"),
    (
        ({"body": _requests.ConnectionError("network down")}, "unavailable"),
        ({"status": 500}, "http_error"),
    ),
    ids=["network_error", "http_error"],
)
@responses.activate
def test_update_check_error_stores_result(response_kwargs, expected_error):
    responses.add(responses.POST, UPDATE_CHECK_URL, **response_kwargs)

    update_check.apply(throw=True)

    gs = GlobalSettings()
    assert gs.settings.update_check_result == {"error": expected_error}
    assert gs.settings.update_check_last is not None


@pytest.mark.django_db
@responses.activate
def test_update_check_sends_email():
    """When an update is available and an email is configured, send a
    notification email."""
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_updatable
    )
    update_check.apply(throw=True)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()


@pytest.mark.django_db
@responses.activate
def test_update_check_no_email_on_same_result():
    """When the update result hasn't changed, do not send another email."""
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_updatable
    )

    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1

    update_check.apply(throw=True)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@responses.activate
def test_update_check_sends_email_on_changed_result():
    """When the update result changes, send a new notification email."""
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, UPDATE_CHECK_URL, callback=_response_updatable
        )
        update_check.apply(throw=True)
        assert len(djmail.outbox) == 1

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, UPDATE_CHECK_URL, callback=_response_not_updatable
        )
        update_check.apply(throw=True)
        assert len(djmail.outbox) == 1

    with responses.RequestsMock() as rsps:
        rsps.add_callback(
            responses.POST, UPDATE_CHECK_URL, callback=_response_updatable
        )
        update_check.apply(throw=True)
        assert len(djmail.outbox) == 2


@pytest.mark.django_db
@responses.activate
def test_update_check_sends_payload():
    """Verify the payload sent to the update server contains the expected
    fields: id, version, events, and plugins."""
    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_not_updatable
    )

    update_check.apply(throw=True)

    assert len(responses.calls) == 1
    payload = json.loads(responses.calls[0].request.body)
    assert payload["version"] == __version__
    assert payload["events"] == {"total": 0, "public": 0}
    assert {"name": "tests.dummy_app", "version": "0.0.0"} in payload["plugins"]
    assert all("name" in p and "version" in p for p in payload["plugins"])
    assert len(payload["id"]) == 32


@pytest.mark.django_db
def test_send_update_notification_email_no_email_configured():
    """If no email is configured, send nothing."""
    gs = GlobalSettings()
    gs.settings.update_check_email = ""
    djmail.outbox = []

    send_update_notification_email()

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_send_update_notification_email_sends():
    gs = GlobalSettings()
    gs.settings.update_check_email = "admin@example.com"
    djmail.outbox = []

    send_update_notification_email()

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["admin@example.com"]
    assert "update" in djmail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_check_result_table_no_result():
    assert check_result_table() == {"error": "no_result"}


@pytest.mark.django_db
def test_check_result_table_error_result():
    gs = GlobalSettings()
    gs.settings.update_check_result = {"error": "unavailable"}

    assert check_result_table() == {"error": "unavailable"}


@pytest.mark.django_db
@responses.activate
def test_check_result_table_no_updates():
    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_not_updatable
    )
    update_check.apply(throw=True)

    table = check_result_table()

    assert table[0] == ("pretalx", __version__, "1.0.0", False)
    plugin_row = next(r for r in table if "Test Dummy Plugin" in str(r[0]))
    assert plugin_row[1] == "0.0.0"
    assert plugin_row[2] == "?"
    assert plugin_row[3] is False


@pytest.mark.django_db
@responses.activate
def test_check_result_table_with_plugin_update():
    responses.add_callback(
        responses.POST, UPDATE_CHECK_URL, callback=_response_with_plugin
    )
    update_check.apply(throw=True)

    table = check_result_table()

    assert table[0] == ("pretalx", __version__, "1.0.0", True)
    plugin_row = next(r for r in table if "Test Dummy Plugin" in str(r[0]))
    assert plugin_row[1] == "0.0.0"
    assert plugin_row[2] == "1.1.1"
    assert plugin_row[3] is True
