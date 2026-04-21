# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import socket
from contextlib import contextmanager
from smtplib import SMTPResponseException, SMTPSenderRefused
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail as djmail
from django.core.mail import get_connection
from django.test import override_settings

from pretalx.common.exceptions import SendMailException
from pretalx.common.mail import (
    CustomSMTPBackend,
    TolerantDict,
    _format_email,
    _mark_mail_failed,
    _mark_mail_sent,
    mail_send_task,
)
from pretalx.event.models import Event
from pretalx.mail.models import QueuedMailStates
from tests.factories import EventFactory, QueuedMailFactory

pytestmark = pytest.mark.unit


def test_tolerant_dict_existing_key_returns_value():
    d = TolerantDict({"name": "Alice", "role": "speaker"})

    assert d["name"] == "Alice"
    assert d["role"] == "speaker"


def test_tolerant_dict_missing_key_returns_key_string():
    d = TolerantDict({"name": "Alice"})

    assert d["missing"] == "missing"


def test_format_email_with_display_name_preserves_it():
    result = _format_email("Custom Name <test@test.org>", "Fallback")

    assert result == "Custom Name <test@test.org>"


def test_format_email_without_display_name_uses_fallback():
    result = _format_email("test@test.org", "Fallback Name")

    assert result == "Fallback Name <test@test.org>"


@pytest.mark.django_db
def test_mark_mail_sent_updates_state(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    _mark_mail_sent(mail.pk)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


@pytest.mark.django_db
def test_mark_mail_sent_nonexistent_does_not_raise():
    _mark_mail_sent(999999)


@pytest.mark.django_db
def test_mark_mail_failed_updates_state_and_records_error(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    _mark_mail_failed(mail.pk, RuntimeError("Connection refused"))
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data == {"error": "Connection refused", "type": "RuntimeError"}


@pytest.mark.django_db
def test_mark_mail_failed_nonexistent_does_not_raise():
    _mark_mail_failed(999999, RuntimeError("test"))


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_mail_send_task_with_event(event):
    """reply_to falls back to the event's email when sender equals
    MAIL_FROM and no custom reply_to is set."""
    djmail.outbox = []

    mail_send_task("recipient@test.org", "Subject", "Body", None, event=event.pk)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["recipient@test.org"]
    assert djmail.outbox[0].subject == "Subject"
    assert djmail.outbox[0].body == "Body"
    assert djmail.outbox[0].from_email == f"{event.name} <orga@orga.org>"
    assert djmail.outbox[0].reply_to == [f"{event.name} <{event.email}>"]


@pytest.mark.parametrize(
    ("reply_to_setting", "expected_reply_to"),
    (
        ("reply@test.org", "{event_name} <reply@test.org>"),
        ("Custom Reply <reply@test.org>", "Custom Reply <reply@test.org>"),
    ),
)
@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_mail_send_task_event_custom_reply_to(reply_to_setting, expected_reply_to):
    event = EventFactory(mail_settings={"reply_to": reply_to_setting})
    djmail.outbox = []

    mail_send_task("recipient@test.org", "S", "B", None, event=event.pk)

    assert djmail.outbox[0].reply_to == [
        expected_reply_to.format(event_name=event.name)
    ]


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_mail_send_task_caller_reply_to_overrides_event():
    event = EventFactory(mail_settings={"reply_to": "event-reply@test.org"})
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org", "S", "B", None, reply_to="caller@test.org", event=event.pk
    )

    assert djmail.outbox[0].reply_to == ["caller@test.org"]


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_mail_send_task_reply_to_comma_separated_string(event):
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org",
        "S",
        "B",
        None,
        reply_to="a@test.org,b@test.org",
        event=event.pk,
    )

    assert djmail.outbox[0].reply_to == ["a@test.org", "b@test.org"]


@pytest.mark.parametrize(
    ("mail_from", "expected_from"),
    (
        ("orga@orga.org", "pretalx <orga@orga.org>"),
        ("Custom Sender <orga@orga.org>", "Custom Sender <orga@orga.org>"),
    ),
)
@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_without_event(mail_from, expected_from):
    djmail.outbox = []

    with override_settings(MAIL_FROM=mail_from):
        mail_send_task("recipient@test.org", "Subject", "Body", None)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].from_email == expected_from
    assert djmail.outbox[0].reply_to == []


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_empty_address_exits_early():
    djmail.outbox = []

    result = mail_send_task("", "Subject", "Body", None)

    assert result is None
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_filters_empty_addresses_from_list(event):
    djmail.outbox = []

    mail_send_task(
        ["", "recipient@test.org", ""], "Subject", "Body", None, event=event.pk
    )

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["recipient@test.org"]


@pytest.mark.parametrize(
    "subject",
    (
        "Talk about\x0bthings",
        "Talk about\nthings",
        "Talk about\r\nthings",
        "Talk about\x00things",
        "Talk about\x7fthings",
    ),
)
@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_strips_control_chars_from_subject(event, subject):
    djmail.outbox = []

    mail_send_task("recipient@test.org", subject, "Body", None, event=event.pk)

    assert djmail.outbox[0].subject == "Talk about things"


@pytest.mark.parametrize(
    "address", ("user@localhost", "user@example.org", "user@example.com")
)
@override_settings(
    DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
)
def test_mail_send_task_filters_debug_domains_in_production(address):
    assert mail_send_task(address, "S", "B", None) is None


@pytest.mark.django_db
@override_settings(
    DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
def test_mail_send_task_allows_debug_domains_in_debug_mode():
    djmail.outbox = []

    mail_send_task("user@localhost", "S", "B", None)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["user@localhost"]


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_allows_debug_domains_with_locmem_backend():
    djmail.outbox = []

    mail_send_task("user@example.com", "S", "B", None)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["user@example.com"]


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_attaches_html_alternative(event):
    djmail.outbox = []
    html = "<html><body><p>Hello</p></body></html>"

    mail_send_task("recipient@test.org", "S", "B", html, event=event.pk)

    assert len(djmail.outbox[0].alternatives) == 1
    content, mimetype = djmail.outbox[0].alternatives[0]
    assert mimetype == "text/html"
    assert "Hello" in content


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_no_html_no_alternative(event):
    djmail.outbox = []

    mail_send_task("recipient@test.org", "S", "B", None, event=event.pk)

    assert djmail.outbox[0].alternatives == []


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_with_attachments(event):
    djmail.outbox = []
    attachments = [
        {"name": "file.txt", "content": "hello world", "content_type": "text/plain"}
    ]

    mail_send_task(
        "recipient@test.org", "S", "B", None, event=event.pk, attachments=attachments
    )

    assert len(djmail.outbox[0].attachments) == 1
    name, content, content_type = djmail.outbox[0].attachments[0]
    assert name == "file.txt"
    assert content == "hello world"
    assert content_type == "text/plain"


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_with_cc_and_bcc(event):
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org",
        "S",
        "B",
        None,
        event=event.pk,
        cc=["cc@test.org"],
        bcc=["bcc@test.org"],
    )

    assert djmail.outbox[0].cc == ["cc@test.org"]
    assert djmail.outbox[0].bcc == ["bcc@test.org"]


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_with_custom_headers(event):
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org",
        "S",
        "B",
        None,
        event=event.pk,
        headers={"X-Custom": "value"},
    )

    assert djmail.outbox[0].extra_headers == {"X-Custom": "value"}


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_marks_queued_mail_sent_on_success(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org", "S", "B", None, event=event.pk, queued_mail_id=mail.pk
    )
    mail.refresh_from_db()

    assert len(djmail.outbox) == 1
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


@pytest.mark.parametrize("rcpt_code", (250, 251))
def test_custom_smtp_backend_test_success(rcpt_code):
    """rcpt code 251 (will forward) is also accepted."""
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = (250, b"OK")
    mock_conn.rcpt.return_value = (rcpt_code, b"OK")

    # Mocking open/close: this method talks directly to an SMTP server,
    # which is unavailable in tests (system boundary).
    with patch.object(backend, "open"), patch.object(backend, "close"):
        backend.connection = mock_conn
        backend.test("sender@test.org")


@pytest.mark.parametrize(
    ("mail_response", "rcpt_response"),
    (((550, b"Rejected"), (250, b"OK")), ((250, b"OK"), (550, b"Rejected"))),
)
def test_custom_smtp_backend_test_rejected(mail_response, rcpt_response):
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = mail_response
    mock_conn.rcpt.return_value = rcpt_response

    # Mocking open/close: SMTP server unavailable in tests (system boundary).
    with patch.object(backend, "open"), patch.object(backend, "close"):
        backend.connection = mock_conn
        with pytest.raises(SMTPSenderRefused) as exc_info:
            backend.test("sender@test.org")

    assert exc_info.value.smtp_code == 550


def test_custom_smtp_backend_test_closes_on_error():
    backend = CustomSMTPBackend(host="localhost", port=25)
    mock_conn = MagicMock()
    mock_conn.mail.return_value = (550, b"Rejected")

    # Mocking open/close: SMTP server unavailable in tests (system boundary).
    # We track close() to verify cleanup happens in the finally block.
    with patch.object(backend, "open"):
        backend.connection = mock_conn
        with pytest.raises(SMTPSenderRefused):
            backend.test("sender@test.org")

    # close() is a real method on the backend — verify it set connection to None
    assert backend.connection is None


# One getaddrinfo result per private/local/multicast/link-local address class.
# Ported verbatim from pretix PR #6073 (src/tests/base/test_mail.py).
PRIVATE_IPS_RES = [
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.3", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.1.1.1", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.5.3", 443))],
    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("224.0.0.1", 443))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("ff00::1", 443, 0, 0))],
    [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fc00::1", 443, 0, 0))],
]


@contextmanager
def assert_mail_connection(res, should_connect, use_ssl):
    """Mock the SMTP socket/SSL plumbing and assert whether connect() ran."""
    with (
        patch("socket.socket") as mock_socket,
        patch("socket.getaddrinfo", return_value=res),
        patch("smtplib.SMTP.getreply", return_value=(220, b"")),
        patch("smtplib.SMTP.sendmail"),
        patch("ssl.SSLContext.wrap_socket") as mock_ssl,
    ):
        yield

        if should_connect:
            mock_socket.assert_called_once()
            mock_socket.return_value.connect.assert_called_once_with(res[0][-1])
            if use_ssl:
                mock_ssl.assert_called_once()
        else:
            mock_socket.assert_not_called()
            mock_socket.return_value.connect.assert_not_called()
            mock_ssl.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("res", PRIVATE_IPS_RES)
@pytest.mark.parametrize("use_ssl", (True, False))
def test_custom_smtp_backend_blocks_private_ip(res, use_ssl):
    with (
        assert_mail_connection(res=res, should_connect=False, use_ssl=use_ssl),
        pytest.raises(OSError, match="Request to .* blocked"),
    ):
        CustomSMTPBackend(host="smtp.example.com", use_ssl=use_ssl).open()


@pytest.mark.django_db
@pytest.mark.parametrize("use_ssl", (True, False))
def test_custom_smtp_backend_public_ip_allowed(use_ssl):
    public_res = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    with assert_mail_connection(res=public_res, should_connect=True, use_ssl=use_ssl):
        CustomSMTPBackend(host="smtp.example.com", use_ssl=use_ssl).open()


@pytest.mark.parametrize(
    ("custom_mail_from", "expected_email_addr"),
    (("custom@example.com", "custom@example.com"), ("", "orga@orga.org")),
)
@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_mail_send_task_event_custom_smtp_sender(custom_mail_from, expected_email_addr):
    event = EventFactory(
        mail_settings={"smtp_use_custom": True, "mail_from": custom_mail_from}
    )
    djmail.outbox = []

    # Mocking get_mail_backend: smtp_use_custom creates a CustomSMTPBackend
    # that connects to a real SMTP server, unavailable in tests (system boundary).
    with patch.object(
        Event, "get_mail_backend", return_value=get_connection(fail_silently=False)
    ):
        mail_send_task("recipient@test.org", "S", "B", None, event=event.pk)

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].from_email == f"{event.name} <{expected_email_addr}>"


@pytest.mark.parametrize(
    "exception",
    (SMTPResponseException(500, b"Error"), ConnectionError("Connection refused")),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_send_error_without_queued_mail_raises(exception):
    # Mocking get_connection: need to simulate send failure, which is
    # impossible with the locmem backend (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with (
        patch("pretalx.common.mail.get_connection", return_value=mock_backend),
        pytest.raises(SendMailException),
    ):
        mail_send_task("recipient@test.org", "S", "B", None)


@pytest.mark.parametrize(
    ("exception", "expected_error_type"),
    (
        (SMTPResponseException(500, b"Error"), "SMTPResponseException"),
        (ConnectionError("Connection refused"), "ConnectionError"),
    ),
)
@pytest.mark.django_db
@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_send_error_with_queued_mail_marks_failed(
    event, exception, expected_error_type
):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    # Mocking get_connection: need to simulate send failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with patch("pretalx.common.mail.get_connection", return_value=mock_backend):
        mail_send_task("recipient@test.org", "S", "B", None, queued_mail_id=mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == expected_error_type


@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_retryable_smtp_error_without_queued_mail_raises():
    # Mocking get_connection: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch("pretalx.common.mail.get_connection", return_value=mock_backend),
        # Mocking retry: in test mode, celery retry() raises Retry which
        # triggers recursive re-execution. We simulate exhausted retries
        # directly to test the error handling path without 5 recursive calls.
        patch.object(
            mail_send_task,
            "retry",
            side_effect=mail_send_task.MaxRetriesExceededError(),
        ),
        pytest.raises(mail_send_task.MaxRetriesExceededError),
    ):
        mail_send_task("recipient@test.org", "S", "B", None)


@pytest.mark.django_db
@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_retryable_smtp_error_with_queued_mail_marks_failed(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    # Mocking get_connection: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch("pretalx.common.mail.get_connection", return_value=mock_backend),
        # Mocking retry: simulate exhausted retries directly (see comment
        # in test above).
        patch.object(
            mail_send_task,
            "retry",
            side_effect=mail_send_task.MaxRetriesExceededError(),
        ),
    ):
        mail_send_task("recipient@test.org", "S", "B", None, queued_mail_id=mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "SMTPResponseException"
