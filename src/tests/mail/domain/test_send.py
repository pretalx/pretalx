# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

from unittest.mock import patch

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.core.mail import get_connection
from django.test import override_settings
from django.utils.timezone import now as tz_now

from pretalx.event.models import Event
from pretalx.mail import tasks as mail_tasks
from pretalx.mail.domain.send import (
    _format_email,
    build_message,
    filter_recipients,
    resolve_envelope,
    send_queued_mail,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import queuedmail_pre_send
from tests.factories import EventFactory, QueuedMailFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("state", (QueuedMailStates.SENT, QueuedMailStates.SENDING))
def test_send_non_draft_raises(event, state):
    mail = QueuedMailFactory(event=event, state=state, to="a@b.com")
    with pytest.raises(ValidationError):
        mail.send()


def test_send_delivers_email(event):
    """Sending a persisted draft mail dispatches it via the celery task,
    which delivers the email and marks the mail as sent."""
    djmail.outbox = []
    user = UserFactory()
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")
    mail.to_users.add(user)

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert set(sent_email.to) == {"test@pretalx.org", user.email}
    assert sent_email.subject == mail.prefixed_subject
    assert mail.text in sent_email.body


def test_send_non_persisted_delivers_email(event):
    """A non-persisted mail (created with commit=False) goes through the
    fire-and-forget path, setting sent and state in-memory."""
    djmail.outbox = []
    mail = QueuedMail(
        event=event, to="test@pretalx.org", subject="Test", text="Body", locale="en"
    )

    mail.send()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1


def test_send_without_event_delivers_email():
    """A persisted mail without an event skips the pre_send signal but
    still dispatches the celery task."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=None, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


def test_send_skips_dispatch_when_signal_sets_sent(event, register_signal_handler):
    """When a pre_send signal handler sets mail.sent, send() returns early
    without dispatching the celery task again."""

    def mark_as_sent(signal, sender, mail, **kwargs):
        mail.sent = tz_now()

    register_signal_handler(queuedmail_pre_send, mark_as_sent)
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 0


def test_send_broker_failure_marks_failed(event, monkeypatch):
    """When the celery broker is unreachable (OSError), the mail is marked
    as failed rather than crashing."""

    def broken_broker(**kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(mail_tasks.mail_send_task, "apply_async", broken_broker)
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Broker unavailable" in mail.error_data["error"]


def test_send_after_failure_clears_error(event):
    """When a previously failed mail is sent again, the error data and
    timestamp are cleared on successful dispatch."""
    djmail.outbox = []
    mail = QueuedMailFactory(
        event=event,
        to="test@pretalx.org",
        error_data={"error": "previous failure"},
        error_timestamp="2024-01-01T00:00:00Z",
    )
    assert mail.has_error is True

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.error_data is None
    assert mail.error_timestamp is None


def test_send_with_comma_separated_to(event):
    """When the 'to' field contains comma-separated addresses, all of them
    receive the email."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="a@example.com,b@example.com")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
    assert set(djmail.outbox[0].to) == {"a@example.com", "b@example.com"}


def test_send_queued_mail_callable_directly(event):
    """The domain function works without going through the model thin
    method."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_queued_mail(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


def test_format_email_with_display_name_preserves_it():
    assert (
        _format_email("Custom Name <test@test.org>", "Fallback")
        == "Custom Name <test@test.org>"
    )


def test_format_email_without_display_name_uses_fallback():
    assert (
        _format_email("test@test.org", "Fallback Name")
        == "Fallback Name <test@test.org>"
    )


def test_filter_recipients_empty_string_returns_empty_list():
    assert filter_recipients("") == []


def test_filter_recipients_wraps_string_into_list():
    assert filter_recipients("user@test.org") == ["user@test.org"]


def test_filter_recipients_drops_empty_addresses_from_list():
    assert filter_recipients(["", "user@test.org", ""]) == ["user@test.org"]


@pytest.mark.parametrize(
    "address", ("user@localhost", "user@example.org", "user@example.com")
)
@override_settings(
    DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
)
def test_filter_recipients_drops_debug_domains_in_production(address):
    assert filter_recipients(address) == []


@override_settings(
    DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
def test_filter_recipients_allows_debug_domains_in_debug_mode():
    assert filter_recipients("user@localhost") == ["user@localhost"]


@override_settings(
    DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
def test_filter_recipients_allows_debug_domains_with_locmem_backend():
    assert filter_recipients("user@example.com") == ["user@example.com"]


@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_event_default_reply_to(event):
    """When no reply_to is given and sender equals MAIL_FROM, reply_to falls
    back to the event's email address."""
    sender, reply_to, _backend = resolve_envelope(event, None)

    assert sender == f"{event.name} <orga@orga.org>"
    assert reply_to == [f"{event.name} <{event.email}>"]


@pytest.mark.parametrize(
    ("reply_to_setting", "expected_reply_to"),
    (
        ("reply@test.org", "{event_name} <reply@test.org>"),
        ("Custom Reply <reply@test.org>", "Custom Reply <reply@test.org>"),
    ),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_event_custom_reply_to(reply_to_setting, expected_reply_to):
    event = EventFactory(mail_settings={"reply_to": reply_to_setting})

    _sender, reply_to, _backend = resolve_envelope(event, None)

    assert reply_to == [expected_reply_to.format(event_name=event.name)]


@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_caller_reply_to_overrides_event():
    event = EventFactory(mail_settings={"reply_to": "event-reply@test.org"})

    _sender, reply_to, _backend = resolve_envelope(event, "caller@test.org")

    assert reply_to == ["caller@test.org"]


@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_reply_to_comma_separated_string(event):
    _sender, reply_to, _backend = resolve_envelope(event, "a@test.org,b@test.org")

    assert reply_to == ["a@test.org", "b@test.org"]


@pytest.mark.parametrize(
    ("mail_from", "expected_from"),
    (
        ("orga@orga.org", "pretalx <orga@orga.org>"),
        ("Custom Sender <orga@orga.org>", "Custom Sender <orga@orga.org>"),
    ),
)
def test_resolve_envelope_without_event(mail_from, expected_from):
    with override_settings(MAIL_FROM=mail_from):
        sender, reply_to, _backend = resolve_envelope(None, None)

    assert sender == expected_from
    assert reply_to == []


@pytest.mark.parametrize(
    ("custom_mail_from", "expected_email_addr"),
    (("custom@example.com", "custom@example.com"), ("", "orga@orga.org")),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_event_custom_smtp_sender(
    custom_mail_from, expected_email_addr
):
    event = EventFactory(
        mail_settings={"smtp_use_custom": True, "mail_from": custom_mail_from}
    )

    # Mocking get_mail_backend: smtp_use_custom returns a CustomSMTPBackend
    # that connects to a real SMTP server (system boundary).
    with patch.object(
        Event, "get_mail_backend", return_value=get_connection(fail_silently=False)
    ):
        sender, _reply_to, _backend = resolve_envelope(event, None)

    assert sender == f"{event.name} <{expected_email_addr}>"


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
def test_build_message_strips_control_chars_from_subject(subject):
    email = build_message(
        to=["user@test.org"],
        subject=subject,
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
    )

    assert email.subject == "Talk about things"


def test_build_message_inlines_html_alternative():
    html = "<html><head><style>p { color: red; }</style></head><body><p>Hello</p></body></html>"

    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=html,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
    )

    assert len(email.alternatives) == 1
    content, mimetype = email.alternatives[0]
    assert mimetype == "text/html"
    assert "Hello" in content
    assert 'style="color: red' in content


def test_build_message_without_html_attaches_no_alternative():
    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
    )

    assert email.alternatives == []


def test_build_message_attaches_files():
    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
        attachments=[
            {"name": "file.txt", "content": "hello world", "content_type": "text/plain"}
        ],
    )

    assert len(email.attachments) == 1
    name, content, content_type = email.attachments[0]
    assert name == "file.txt"
    assert content == "hello world"
    assert content_type == "text/plain"


def test_build_message_with_cc_and_bcc():
    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
        cc=["cc@test.org"],
        bcc=["bcc@test.org"],
    )

    assert email.cc == ["cc@test.org"]
    assert email.bcc == ["bcc@test.org"]


def test_build_message_with_custom_headers():
    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
        headers={"X-Custom": "value"},
    )

    assert email.extra_headers == {"X-Custom": "value"}
