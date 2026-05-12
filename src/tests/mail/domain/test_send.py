# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

from unittest.mock import MagicMock, patch

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.core.mail import get_connection
from django.test import override_settings
from django.utils.safestring import mark_safe
from django.utils.timezone import now as tz_now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretalx.common.exceptions import SendMailException
from pretalx.mail import tasks as mail_tasks
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
from tests.factories import EventFactory, QueuedMailFactory, UserFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("state", (QueuedMailStates.SENT, QueuedMailStates.SENDING))
def test_send_draft_non_draft_raises(event, state):
    mail = QueuedMailFactory(event=event, state=state, to="a@b.com")
    with pytest.raises(ValidationError):
        send_draft(mail)


def test_send_draft_delivers_email(event):
    """Sending a persisted draft mail dispatches it via the celery task,
    which delivers the email and marks the mail as sent."""
    djmail.outbox = []
    user = UserFactory()
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")
    mail.to_users.add(user)

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert set(sent_email.to) == {"test@pretalx.org", user.email}
    assert sent_email.subject == mail.prefixed_subject
    assert mail.text in sent_email.body


def test_send_transient_delivers_email(event):
    """A non-persisted mail goes through the fire-and-forget path,
    setting sent and state in-memory."""
    djmail.outbox = []
    mail = QueuedMail(
        event=event,
        to="test@pretalx.org",
        subject=mark_safe("Test"),
        text=mark_safe("Body"),
        locale="en",
    )

    send_transient(mail)

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1


def test_send_draft_without_event_delivers_email():
    """A persisted mail without an event skips the pre_send signal but
    still dispatches the celery task."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=None, to="test@pretalx.org")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


def test_send_draft_skips_when_signal_sets_sent(event, register_signal_handler):
    """When a pre_send signal handler sets mail.sent, send_draft
    returns early without dispatching the celery task again."""

    def mark_as_sent(signal, sender, mail, **kwargs):
        mail.sent = tz_now()

    register_signal_handler(queuedmail_pre_send, mark_as_sent)
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 0


def test_send_draft_broker_failure_marks_failed(event, monkeypatch):
    """When the celery broker is unreachable (OSError), the mail is marked
    as failed rather than crashing."""

    def broken_broker(*args, **kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(mail_tasks.task_send_draft, "apply_async", broken_broker)
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Broker unavailable" in mail.error_data["error"]


def test_send_draft_logs_after_dispatch_succeeds(event):
    """The ``pretalx.mail.sent`` activity log entry is written only after
    the worker task is queued — a broker outage that triggers
    :func:`mark_failed` must not leave a misleading 'sent' audit row.
    """
    from pretalx.common.models.log import ActivityLog  # noqa: PLC0415

    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    with patch.object(
        mail_tasks.task_send_draft, "apply_async", side_effect=OSError("broker down")
    ):
        send_draft(mail)

    with scopes_disabled():
        assert not ActivityLog.objects.filter(
            action_type="pretalx.mail.sent", object_id=mail.pk
        ).exists()
    mail.refresh_from_db()
    assert mail.has_error is True


def test_queued_mail_send_emits_deprecation_warning(event):
    """``QueuedMail.send`` is a compatibility shim for plugins; calling
    it from new code must surface as a DeprecationWarning."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    with pytest.warns(DeprecationWarning, match="QueuedMail.send is deprecated"):
        mail.send()


def test_queued_mail_send_routes_unsaved_through_send_transient(event):
    """The deprecated shim routes unsaved mails to ``send_transient`` so
    plugins relying on the old fire-and-forget behaviour keep working."""
    djmail.outbox = []
    mail = QueuedMail(
        event=event,
        to="test@pretalx.org",
        subject=mark_safe("S"),
        text=mark_safe("B"),
        locale="en",
    )

    with pytest.warns(DeprecationWarning, match="QueuedMail.send is deprecated"):
        mail.send()

    assert mail.pk is None
    assert len(djmail.outbox) == 1


def test_send_draft_requires_persisted_mail(event):
    """An unsaved mail can never be a draft — it has no row to mark
    SENDING and no pk to hand the worker. Catch the misuse loudly."""
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
    """``send_transient`` is the unsaved-mail path; handing it a row would
    bypass the SENDING/SENT state machine and double-deliver."""
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")
    with pytest.raises(RuntimeError, match="must not be called on a persisted mail"):
        send_transient(mail)


def test_send_transient_broker_failure_logs_and_swallows(event, caplog, monkeypatch):
    """A broker outage on the transient path is fire-and-forget: log and
    move on. There is no row to mark and no caller waiting for an
    exception, so swallowing keeps the request flow alive."""
    monkeypatch.setattr(
        mail_tasks.task_send_transient,
        "apply_async",
        MagicMock(side_effect=OSError("Broker unavailable")),
    )
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


def test_send_transient_forwards_bcc_from_template(event):
    """Regression: a transient mail rendered from a template with ``bcc``
    set must carry that bcc through to the dispatched task. The earlier
    refactor dropped the parameter and silenced organiser-configured bcc
    addresses on configurable system mails (NEW_SUBMISSION_INTERNAL,
    DRAFT_REMINDER, …)."""
    from pretalx.mail.domain.render import render_template_to_mail  # noqa: PLC0415
    from tests.factories import MailTemplateFactory  # noqa: PLC0415

    template = MailTemplateFactory(
        event=event, subject="Hi", text="Body", bcc="watch@example.org"
    )
    mail = render_template_to_mail(template)
    mail.to = "test@pretalx.org"

    with patch.object(mail_tasks.task_send_transient, "apply_async") as mock:
        send_transient(mail)

    forwarded = mock.call_args.kwargs["kwargs"]
    assert forwarded["bcc"] == ["watch@example.org"]


def test_send_transient_forwards_event_id_by_default(event):
    """Default routing for ``send_transient`` is the event's SMTP backend:
    the worker receives ``event_id`` so it can look up the event-specific
    connection. ``force_global_backend`` is opt-in for system mails only.
    """
    mail = QueuedMail(
        event=event,
        to="user@example.org",
        subject=mark_safe("S"),
        text=mark_safe("B"),
        locale="en",
    )

    with patch.object(mail_tasks.task_send_transient, "apply_async") as mock:
        send_transient(mail)

    assert mock.call_args.kwargs["kwargs"]["event_id"] == event.pk


def test_send_transient_force_global_backend_strips_event_id(event):
    """``force_global_backend=True`` pins delivery to the global backend
    by withholding ``event_id`` from the worker, so password resets and
    similar system mails survive a broken event SMTP."""
    mail = QueuedMail(
        event=event,
        to="user@example.org",
        subject=mark_safe("S"),
        text=mark_safe("B"),
        locale="en",
    )

    with patch.object(mail_tasks.task_send_transient, "apply_async") as mock:
        send_transient(mail, force_global_backend=True)

    assert mock.call_args.kwargs["kwargs"]["event_id"] is None


def test_send_draft_after_failure_clears_error(event):
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

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.error_data is None
    assert mail.error_timestamp is None


def test_send_draft_with_comma_separated_to(event):
    """When the 'to' field contains comma-separated addresses, all of them
    receive the email."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="a@example.com,b@example.com")

    send_draft(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
    assert set(djmail.outbox[0].to) == {"a@example.com", "b@example.com"}


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

    # Mocking mail_backend_for_event: smtp_use_custom returns a CustomSMTPBackend
    # that connects to a real SMTP server (system boundary).
    with patch(
        "pretalx.mail.domain.smtp.mail_backend_for_event",
        return_value=get_connection(fail_silently=False),
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


def _fake_user(name):
    class _U:
        def __init__(self, name):
            self.name = name
            self.email = f"{name.lower()}@example.org"
            self.locale = "en"

    return _U(name)


def test_send_system_mail_dispatches_without_event():
    djmail.outbox = []

    send_system_mail(
        subject="Account update",
        text="Hi {name}, your account is fine.",
        to="user@example.org",
        context_kwargs={"user": _fake_user("Alex")},
    )

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == ["user@example.org"]
    assert sent.subject == "Account update"
    assert "Hi Alex" in sent.body


def test_send_system_mail_routes_via_transient_task():
    """``send_system_mail`` ships the rendered body through
    ``task_send_transient`` and never touches the queued
    dispatch path (no row to reload)."""
    with patch.object(mail_tasks.task_send_transient, "apply_async") as mock:
        send_system_mail(subject="Reset", text="Body", to="user@example.org")

    mock.assert_called_once()
    forwarded = mock.call_args.kwargs["kwargs"]
    assert forwarded["to"] == ["user@example.org"]
    assert forwarded["event_id"] is None


def test_send_system_mail_does_not_persist(event):
    djmail.outbox = []
    before = QueuedMail.objects.count()

    send_system_mail(
        subject="System notice",
        text="Body for {event_name}.",
        to="user@example.org",
        event=event,
    )

    assert QueuedMail.objects.count() == before
    assert len(djmail.outbox) == 1


def test_send_system_mail_renders_event_placeholders(event):
    djmail.outbox = []

    send_system_mail(
        subject="Hello",
        text="Greetings from {event_name}.",
        to="user@example.org",
        event=event,
    )

    assert str(event.name) in djmail.outbox[0].body


def test_send_system_mail_uses_event_signature_in_body(event):
    """When event is passed, the rendered body carries the event's
    signature — the event still drives content styling."""
    event.mail_settings = {**event.mail_settings, "signature": "-- \nThe team"}
    event.save()
    djmail.outbox = []

    send_system_mail(subject="Hi", text="Body.", to="user@example.org", event=event)

    assert "The team" in djmail.outbox[0].body


def test_send_system_mail_ignores_event_smtp(event):
    """Even with an event, system mail must use the default backend / sender
    and must not pick up the event's reply-to — never the event's SMTP."""
    event.mail_settings = {
        **event.mail_settings,
        "smtp_use_custom": True,
        "mail_from": "event-smtp@example.org",
        "reply_to": "event-replyto@example.org",
    }
    event.save()
    djmail.outbox = []

    send_system_mail(subject="Hi", text="Body.", to="user@example.org", event=event)

    sent = djmail.outbox[0]
    assert "event-smtp@example.org" not in sent.from_email
    assert sent.reply_to == []


def test_send_system_mail_does_not_fire_signals(event, register_signal_handler):
    handler = MagicMock()
    register_signal_handler(queuedmail_pre_send, handler)
    register_signal_handler(queuedmail_post_send, handler)
    djmail.outbox = []

    send_system_mail(subject="Hi", text="Body.", to="user@example.org", event=event)

    handler.assert_not_called()


def test_send_system_mail_collapses_lazy_i18n_with_locale(event):
    """``locale`` is forwarded to the renderer; ``LazyI18nString`` resolves
    to that language without the caller needing an outer ``override``."""
    subject = LazyI18nString({"en": "Hello", "de": "Hallo"})
    djmail.outbox = []

    send_system_mail(
        subject=subject, text="Body.", to="user@example.org", event=event, locale="de"
    )

    assert djmail.outbox[0].subject.endswith("Hallo")


def test_send_system_mail_safe_extra_context_renders():
    djmail.outbox = []

    send_system_mail(
        subject="Reset",
        text="Click {url}",
        to="user@example.org",
        safe_extra_context={"url": mark_safe("https://example.org/reset/abc")},
    )

    assert "https://example.org/reset/abc" in djmail.outbox[0].body


def test_send_system_mail_empty_recipient_raises():
    """A blank recipient at dispatch time is programmer error: the
    transient dispatch helper rejects it rather than silently dropping
    the mail."""
    djmail.outbox = []

    with pytest.raises(ValueError, match="empty mail.to"):
        send_system_mail(subject="Hi", text="Body.", to="")

    assert djmail.outbox == []


def test_get_send_mail_exceptions_returns_none_without_handlers(event):
    request = make_request(event)

    assert get_send_mail_exceptions(request) is None


def test_get_send_mail_exceptions_returns_errors(event, register_signal_handler):
    def raise_exception(signal, sender, **kwargs):
        raise SendMailException("Blocked!")

    register_signal_handler(request_pre_send, raise_exception)
    request = make_request(event)

    assert get_send_mail_exceptions(request) == ["Blocked!"]
