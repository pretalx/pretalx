"""Server logs: the plugin's actions are traceable, without personal data."""

import logging
import re
from unittest import mock

import pytest
from django.test import Client
from pretalx_pretix_sso import tickets

PLUGIN_LOGGER = "pretalx_pretix_sso"
PERSONAL_DATA = (
    "@example.invalid",  # any email address used in these tests
    "CUST-SECRET-ID",  # pretix customer identifier (OIDC sub)
    "test-token",
    "test-secret",
)


@pytest.fixture
def plugin_logs(caplog):
    caplog.set_level(logging.DEBUG, logger=PLUGIN_LOGGER)

    def messages(level=logging.DEBUG):
        return [
            r.getMessage()
            for r in caplog.records
            if r.name.startswith(PLUGIN_LOGGER) and r.levelno >= level
        ]

    return messages


def _userinfo(sub="CUST-SECRET-ID", email="speaker@example.invalid"):
    return {"sub": sub, "email": email, "email_verified": True, "name": "Speaker"}


def test_successful_login_is_logged(sso_callback, event, plugin_logs):
    _, request = sso_callback(_userinfo())
    user_code = request.user.code
    assert any(
        "login succeeded" in m and user_code in m and event.slug in m and "created" in m
        for m in plugin_logs(logging.INFO)
    )
    sso_callback(_userinfo())
    assert any("(returning account)" in m for m in plugin_logs(logging.INFO))


def test_refusals_are_logged(sso_callback, event, admin, plugin_logs):
    sso_callback(_userinfo(email=admin.email))
    sso_callback({"sub": "X", "email": "u@example.invalid", "email_verified": False})
    info = plugin_logs(logging.INFO)
    assert any("refused" in m and admin.code in m and "organiser" in m for m in info)
    assert any("refused" in m and "no verified email" in m for m in info)


def test_forged_state_is_a_warning(sso_callback, event, plugin_logs):
    sso_callback(_userinfo(), state="forged")
    assert any("state does not match" in m for m in plugin_logs(logging.WARNING))


def test_error_from_pretix_is_logged_on_one_line(event, plugin_logs):
    from conftest import _prepare
    from django.test import RequestFactory
    from pretalx_pretix_sso import views

    request = RequestFactory().get(
        "/p/pretix-sso/callback/",
        {"state": "st", "error": "access_denied\nFAKE LOG LINE"},
    )
    _prepare(request)
    request.session[views.SESSION_KEY] = {
        "state": "st",
        "nonce": "n",
        "verifier": "v",
        "event": event.slug,
        "next": "",
    }
    views.CallbackView.as_view()(request)
    (line,) = [m for m in plugin_logs(logging.INFO) if "ended at pretix" in m]
    assert "\n" not in line and "access_denied\\nFAKE" in line


def test_ticket_fetch_is_logged_with_counts_and_cache_hits(event, plugin_logs):
    holders = tickets.TicketHolders.from_emails(
        {"a@example.invalid"}, {"CUST-SECRET-ID"}
    )
    with mock.patch.object(tickets, "_fetch_ticket_holders", return_value=holders):
        tickets.ticket_holders(event)
        tickets.ticket_holders(event)
    logs = plugin_logs()
    assert any("Fetching pretix tickets for event" in m for m in logs)
    assert any(
        re.search(r"Fetched pretix tickets for event \S+ in \d+\.\ds$", m) for m in logs
    )
    assert any("served from cache" in m for m in logs)


def test_failed_fetch_is_a_warning(event, plugin_logs):
    import requests

    with (
        mock.patch.object(
            tickets,
            "_fetch_ticket_holders",
            side_effect=requests.ConnectionError("down"),
        ),
        pytest.raises(requests.ConnectionError),
    ):
        tickets.ticket_holders(event)
    assert any("failed after" in m for m in plugin_logs(logging.WARNING))


def test_organiser_actions_are_logged(
    tickets_page, event, admin, make_speaker, make_proposal, plugin_logs
):
    speaker = make_speaker("comp@example.invalid")
    make_proposal("Talk", "accepted", speaker)
    with mock.patch.object(
        tickets,
        "_fetch_ticket_holders",
        return_value=tickets.TicketHolders.from_emails(),
    ):
        tickets_page("post", data={"action": "override_on", "user": speaker.code})
        tickets_page("post", data={"action": "sync_tag"})
    info = plugin_logs(logging.INFO)
    assert any(
        admin.code in m and "set the ticket override" in m and speaker.code in m
        for m in info
    )
    assert any(
        "started the needsTicket tag sync" in m and admin.code in m for m in info
    )
    # the speaker is covered by the override, so nothing needs the tag
    assert any("tag sync on event" in m and "added to 0" in m for m in info)


def test_refused_registration_is_logged(event, plugin_logs):
    event.is_public = True
    event.save()
    client = Client(HTTP_HOST="pretalx.example.invalid")
    client.post(
        f"/{event.slug}/login/",
        {
            "register_name": "X",
            "register_email": "x@example.invalid",
            "register_password": "A-long-pass-123",
            "register_password_repeat": "A-long-pass-123",
        },
        secure=True,
    )
    assert any(
        "Refused registration on the login page" in m for m in plugin_logs(logging.INFO)
    )


def test_logs_contain_no_personal_data(
    sso_callback, tickets_page, event, make_speaker, make_proposal, plugin_logs
):
    # Exercise every logged path with personal data flowing through it
    existing = make_speaker("existing@example.invalid", password="pw")
    sso_callback(_userinfo(sub="CUST-SECRET-ID-2", email="existing@example.invalid"))
    sso_callback(_userinfo())
    sso_callback(_userinfo(sub="CUST-SECRET-ID-3"))  # link moved
    sso_callback(_userinfo(), state="forged")
    make_proposal("Talk", "accepted", existing)
    holders = tickets.TicketHolders.from_emails(
        {"existing@example.invalid"}, {"CUST-SECRET-ID"}
    )
    with mock.patch.object(tickets, "_fetch_ticket_holders", return_value=holders):
        tickets_page(query="?partial=1&refresh=1")
        tickets_page("post", data={"action": "override_on", "user": existing.code})
        tickets_page("post", data={"action": "sync_tag"})

    logs = plugin_logs()
    assert len(logs) > 10
    leaked = [m for m in logs if any(p in m for p in PERSONAL_DATA)]
    assert not leaked, leaked


def test_sync_logs_go_to_stdout_once_and_not_stderr(
    tickets_page, event, make_speaker, make_proposal, capfd
):
    make_proposal("Talk", "accepted", make_speaker("nobody@example.invalid"))
    with mock.patch.object(
        tickets,
        "_fetch_ticket_holders",
        return_value=tickets.TicketHolders.from_emails(),
    ):
        tickets_page("post", data={"action": "sync_tag"})
    out, err = capfd.readouterr()  # file-descriptor level: the real stdout/stderr
    result_lines = [
        line
        for line in out.splitlines()
        if "needsTicket tag sync on event test:" in line
    ]
    assert len(result_lines) == 1, out
    # pretalx's log format: level, time, logger name, module, message
    assert re.match(
        r"INFO \d{4}-\d\d-\d\d [\d:,]+ pretalx_pretix_sso\.tagging tagging needsTicket",
        result_lines[0],
    ), result_lines[0]
    assert "Finished the needsTicket tag sync" in out
    assert "pretalx_pretix_sso" not in err


def test_plugin_logs_still_reach_the_pretalx_log_file():
    from pretalx_pretix_sso.log import PLUGIN_LOGGER

    plugin_logger = logging.getLogger(PLUGIN_LOGGER)
    root_files = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)
    ]
    assert root_files and all(h in plugin_logger.handlers for h in root_files)
    assert plugin_logger.propagate is False  # so nothing is written twice


def test_logging_setup_is_idempotent():
    from pretalx_pretix_sso.log import (
        PLUGIN_LOGGER,
        StdoutHandler,
        configure_plugin_logging,
    )

    configure_plugin_logging()
    configure_plugin_logging()
    handlers = logging.getLogger(PLUGIN_LOGGER).handlers
    assert sum(isinstance(h, StdoutHandler) for h in handlers) == 1


def test_stdout_survives_celery_replacing_sys_stdout(capfd, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdout", io.StringIO())  # what celery's worker does
    logging.getLogger("pretalx_pretix_sso.tasks").info(
        "Running the needsTicket tag sync"
    )
    out, _ = capfd.readouterr()
    assert "Running the needsTicket tag sync" in out
