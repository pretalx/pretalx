# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import datetime as dt
from unittest.mock import patch

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.core.mail import mailers
from django.test import override_settings
from django.utils.safestring import mark_safe
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretalx.common.exceptions import SendMailException
from pretalx.common.models.log import ActivityLog
from pretalx.mail import tasks as mail_tasks
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import (
    get_send_mail_exceptions,
    send_draft,
    send_system_mail,
    send_transient,
)
from pretalx.mail.domain.smtp import (
    _format_email,
    build_message,
    filter_recipients,
    resolve_envelope,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import (
    queuedmail_post_send,
    queuedmail_pre_send,
    request_pre_send,
)
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    UserFactory,
)
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

SENT_AT = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize("state", (QueuedMailStates.SENT, QueuedMailStates.SENDING))
def test_send_draft_non_draft_raises(event, state):
    mail = QueuedMailFactory(event=event, state=state, to="a@b.com")
    with pytest.raises(ValidationError):
        send_draft(mail)


def test_send_draft_delivers_to_addresses_and_reachable_speakers(event):
    djmail.outbox = []
    with scopes_disabled():
        account = SpeakerFactory(event=event)
        contact_override = SpeakerFactory(event=event, email="contact@example.com")
        cleared_override = SpeakerFactory(event=event, email="")
        managed_without_email = SpeakerFactory(event=event, user=None, email=None)
    mail = QueuedMailFactory(
        event=event,
        to="a@example.com,b@example.com",
        error_data={"error": "previous failure"},
        error_timestamp="2024-01-01T00:00:00Z",
    )
    mail.to_speakers.add(
        account, contact_override, cleared_override, managed_without_email
    )
    assert mail.has_error is True

    send_draft(mail)
    mail = QueuedMail.objects.select_related("event").get(pk=mail.pk)

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert mail.error_data is None
    assert mail.error_timestamp is None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert set(sent_email.to) == {
        "a@example.com",
        "b@example.com",
        account.user.email,
        "contact@example.com",
        cleared_override.user.email,
    }
    assert sent_email.subject == mail.prefixed_subject
    assert mail.text in sent_email.body


def test_send_draft_without_event_delivers_email():
    djmail.outbox = []
    mail = QueuedMailFactory(event=None, to="test@pretalx.org")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


@pytest.mark.parametrize(
    ("updates", "expected_state", "expected_db_state"),
    (
        ({"sent": SENT_AT}, QueuedMailStates.SENT, QueuedMailStates.SENT),
        (
            {"sent": SENT_AT, "state": QueuedMailStates.SENT},
            QueuedMailStates.SENT,
            QueuedMailStates.DRAFT,
        ),
        (
            {"sent": SENT_AT, "state": QueuedMailStates.SENDING},
            QueuedMailStates.SENT,
            QueuedMailStates.SENT,
        ),
        (
            {"state": QueuedMailStates.SENT},
            QueuedMailStates.SENT,
            QueuedMailStates.DRAFT,
        ),
        (
            {"state": QueuedMailStates.SENDING},
            QueuedMailStates.SENDING,
            QueuedMailStates.DRAFT,
        ),
    ),
    ids=("sent", "sent+SENT", "sent+SENDING", "SENT", "SENDING"),
)
def test_send_draft_skips_when_signal_handler_sends(
    event, register_signal_handler, updates, expected_state, expected_db_state
):
    def mark_as_sent(signal, sender, mail, **kwargs):
        for attr, value in updates.items():
            setattr(mail, attr, value)

    register_signal_handler(queuedmail_pre_send, mark_as_sent)
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_draft(mail)

    assert mail.state == expected_state
    assert mail.sent == updates.get("sent")
    assert QueuedMail.objects.get(pk=mail.pk).state == expected_db_state
    assert len(djmail.outbox) == 0


def test_send_draft_broker_failure_marks_failed_without_log(event, monkeypatch):
    def broken_broker(*args, **kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(mail_tasks.task_send_draft, "apply_async", broken_broker)
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert mail.error_data == {"error": "Broker unavailable", "type": "OSError"}
    with scopes_disabled():
        assert not ActivityLog.objects.filter(
            action_type="pretalx.mail.sent", object_id=mail.pk
        ).exists()


def test_send_draft_requires_persisted_mail(event):
    mail = QueuedMail(
        event=event,
        to="test@pretalx.org",
        subject=mark_safe("S"),
        text=mark_safe("B"),
        locale="en",
    )
    with pytest.raises(RuntimeError, match="requires a persisted mail"):
        send_draft(mail)


def test_send_transient_rejects_persisted_mail(event):
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")
    with pytest.raises(RuntimeError, match="must not be called on a persisted mail"):
        send_transient(mail)


def test_send_transient_broker_failure_logs_and_swallows(event, caplog, monkeypatch):
    def broken_broker(*args, **kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(mail_tasks.task_send_transient, "apply_async", broken_broker)
    djmail.outbox = []
    mail = QueuedMail(
        event=event,
        to="test@pretalx.org",
        subject=mark_safe("S"),
        text=mark_safe("B"),
        locale="en",
    )

    with caplog.at_level("ERROR", logger="pretalx.mail.domain.send"):
        send_transient(mail)

    assert "Failed to queue transient mail" in caplog.text
    assert mail.sent is None
    assert mail.state == QueuedMailStates.DRAFT


@pytest.mark.parametrize(
    ("force_global_backend", "expected_from", "expected_reply_to"),
    (
        (False, "{event_name} <orga@orga.org>", ["{event_name} <{event_email}>"]),
        (True, "pretalx <orga@orga.org>", []),
    ),
    ids=("event_backend", "global_backend"),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_send_transient_delivers_through_event_or_global_backend(
    event, force_global_backend, expected_from, expected_reply_to
):
    djmail.outbox = []
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Body", bcc="watch@example.org"
    )
    mail = render_template_to_mail(template)
    mail.to = "test@pretalx.org"

    send_transient(mail, force_global_backend=force_global_backend)

    assert mail.pk is None
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert sent_email.to == ["test@pretalx.org"]
    assert sent_email.bcc == ["watch@example.org"]
    assert sent_email.from_email == expected_from.format(event_name=event.name)
    assert sent_email.reply_to == [
        address.format(event_name=event.name, event_email=event.email)
        for address in expected_reply_to
    ]


@pytest.mark.parametrize(
    ("addr", "expected"),
    (
        ("Custom Name <test@test.org>", "Custom Name <test@test.org>"),
        ("test@test.org", "Fallback <test@test.org>"),
    ),
)
def test_format_email_fills_in_missing_display_name(addr, expected):
    assert _format_email(addr, "Fallback") == expected


@pytest.mark.parametrize(
    ("to", "expected"),
    (
        ("", []),
        ("user@test.org", ["user@test.org"]),
        (["", "user@test.org", ""], ["user@test.org"]),
    ),
)
def test_filter_recipients_normalises_to_list(to, expected):
    assert filter_recipients(to) == expected


@pytest.mark.parametrize(
    ("debug", "backend", "address", "expected"),
    (
        (False, "smtp", "user@localhost", []),
        (False, "smtp", "user@example.org", []),
        (False, "smtp", "user@example.com", []),
        (True, "locmem", "user@localhost", ["user@localhost"]),
        (False, "locmem", "user@example.com", ["user@example.com"]),
    ),
)
def test_filter_recipients_drops_debug_domains_only_in_production(
    debug, backend, address, expected
):
    with override_settings(
        DEBUG=debug,
        MAILERS={
            "default": {"BACKEND": f"django.core.mail.backends.{backend}.EmailBackend"}
        },
    ):
        assert filter_recipients(address) == expected


@pytest.mark.parametrize(
    ("reply_to_setting", "reply_to", "expected_reply_to"),
    (
        ("", None, ["{event_name} <{event_email}>"]),
        ("reply@test.org", None, ["{event_name} <reply@test.org>"]),
        ("Custom Reply <reply@test.org>", None, ["Custom Reply <reply@test.org>"]),
        ("event-reply@test.org", "caller@test.org", ["caller@test.org"]),
        ("", "a@test.org,b@test.org", ["a@test.org", "b@test.org"]),
    ),
    ids=("event_default", "setting", "setting_with_name", "caller", "caller_list"),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_resolve_envelope_event_reply_to(reply_to_setting, reply_to, expected_reply_to):
    event = EventFactory(mail_settings={"reply_to": reply_to_setting})

    sender, resolved_reply_to, _backend = resolve_envelope(event, reply_to)

    assert sender == f"{event.name} <orga@orga.org>"
    assert resolved_reply_to == [
        address.format(event_name=event.name, event_email=event.email)
        for address in expected_reply_to
    ]


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

    # Mocking mail_backend_for_event: smtp_use_custom returns a CustomSMTPBackend
    # that connects to a real SMTP server (system boundary).
    with patch(
        "pretalx.mail.domain.smtp.mail_backend_for_event", return_value=mailers.default
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


def test_build_message_sets_envelope_fields_without_html():
    email = build_message(
        to=["user@test.org"],
        subject="S",
        body="Body",
        html=None,
        reply_to=[],
        sender="pretalx <orga@orga.org>",
        cc=["cc@test.org"],
        bcc=["bcc@test.org"],
        headers={"X-Custom": "value"},
    )

    assert email.alternatives == []
    assert email.cc == ["cc@test.org"]
    assert email.bcc == ["bcc@test.org"]
    assert email.extra_headers == {"X-Custom": "value"}


def test_send_system_mail_dispatches_without_event():
    djmail.outbox = []

    send_system_mail(
        subject="Account update",
        text="Hi {name}, click {url}",
        to="user@example.org",
        context_kwargs={"user": UserFactory(name="Alex")},
        safe_extra_context={"url": mark_safe("https://example.org/reset/abc")},
    )

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == ["user@example.org"]
    assert sent.subject == "Account update"
    assert "Hi Alex, click https://example.org/reset/abc" in sent.body


def test_send_system_mail_with_event_renders_context_but_ignores_event_smtp(
    event, register_signal_handler
):
    event.mail_settings = {
        **event.mail_settings,
        "signature": "-- \nThe team",
        "smtp_use_custom": True,
        "mail_from": "event-smtp@example.org",
        "reply_to": "event-replyto@example.org",
    }
    event.save()
    signals_fired = []
    register_signal_handler(
        queuedmail_pre_send, lambda **kwargs: signals_fired.append(kwargs)
    )
    register_signal_handler(
        queuedmail_post_send, lambda **kwargs: signals_fired.append(kwargs)
    )
    djmail.outbox = []
    before = QueuedMail.objects.count()

    send_system_mail(
        subject=LazyI18nString({"en": "Hello", "de": "Hallo"}),
        text="Greetings from {event_name}.",
        to="user@example.org",
        event=event,
        locale="de",
    )

    assert QueuedMail.objects.count() == before
    assert signals_fired == []
    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.subject.endswith("Hallo")
    assert f"Greetings from {event.name}." in sent.body
    assert "The team" in sent.body
    assert "event-smtp@example.org" not in sent.from_email
    assert sent.reply_to == []


def test_send_system_mail_empty_recipient_raises():
    djmail.outbox = []

    with pytest.raises(ValueError, match="empty mail.to"):
        send_system_mail(subject="Hi", text="Body.", to="")

    assert djmail.outbox == []


def test_get_send_mail_exceptions_collects_handler_errors(
    event, register_signal_handler
):
    request = make_request(event)
    assert get_send_mail_exceptions(request) is None

    def raise_exception(signal, sender, **kwargs):
        raise SendMailException("Blocked!")

    register_signal_handler(request_pre_send, raise_exception)

    assert get_send_mail_exceptions(request) == ["Blocked!"]
