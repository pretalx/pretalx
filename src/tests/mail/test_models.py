import smtplib

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.utils.timezone import now as tz_now
from django_scopes import scope, scopes_disabled

from pretalx.common import mail as common_mail
from pretalx.common.exceptions import SendMailException
from pretalx.mail.models import (
    MailTemplate,
    MailTemplateRoles,
    QueuedMail,
    QueuedMailStates,
    can_edit_mail,
    get_prefixed_subject,
)
from pretalx.mail.signals import queuedmail_pre_send
from tests.factories import (
    MailTemplateFactory,
    QueuedMailFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("prefix", "subject", "expected"),
    (
        ("", "Hello world", "Hello world"),
        ("MyConf", "Hello world", "[MyConf] Hello world"),
        ("[MyConf]", "Hello world", "[MyConf] Hello world"),
        ("[MyConf]", "[MyConf] Hello world", "[MyConf] Hello world"),
        ("MyConf", "[MyConf] Hello world", "[MyConf] Hello world"),
    ),
)
@pytest.mark.django_db
def test_get_prefixed_subject_adds_brackets(event, prefix, subject, expected):
    """Subjects are prefixed with brackets; already-bracketed prefixes
    aren't double-wrapped; already-prefixed subjects aren't duplicated."""
    event.mail_settings["subject_prefix"] = prefix
    assert get_prefixed_subject(event, subject) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (QueuedMailStates.DRAFT, True),
        (QueuedMailStates.SENDING, False),
        (QueuedMailStates.SENT, False),
    ),
)
@pytest.mark.django_db
def test_can_edit_mail_allows_only_drafts(state, expected):
    """The can_edit_mail rules predicate allows editing only for draft mails."""
    mail = QueuedMailFactory(state=state)
    assert can_edit_mail(None, mail) is expected


def test_can_edit_mail_rejects_objects_without_state():
    """Objects without a state attribute should not be editable."""
    assert can_edit_mail(None, object()) is False


@pytest.mark.django_db
def test_mail_template_str_contains_event_and_subject(event):
    template = MailTemplateFactory(event=event, subject="Welcome!")
    result = str(template)
    assert event.slug in result
    assert "Welcome!" in result


@pytest.mark.django_db
def test_mail_template_log_parent_is_event(event):
    template = MailTemplateFactory(event=event)
    assert template.log_parent == event


@pytest.mark.django_db
def test_to_mail_with_email_string(event):
    """When user is a string, it's used as the 'to' address."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event)

    assert mail.to == "test@example.com"
    assert mail.subject == "Hi"
    assert mail.text == "Body"
    assert mail.pk is not None


@pytest.mark.django_db
def test_to_mail_with_user_object(event):
    """When user is a User instance, it's added via the to_users M2M."""
    user = UserFactory()
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event)

    assert mail.to is None
    assert mail.pk is not None
    assert list(mail.to_users.all()) == [user]


@pytest.mark.django_db
def test_to_mail_uses_user_locale(event):
    """The mail's locale should default to the user's locale."""
    user = UserFactory(locale="de")
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event)
    assert mail.locale == "de"


@pytest.mark.django_db
def test_to_mail_explicit_locale_overrides_user(event):
    """An explicitly passed locale overrides the user's locale."""
    user = UserFactory(locale="de")
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event, locale="fr")
    assert mail.locale == "fr"


@pytest.mark.django_db
def test_to_mail_allows_none_user_with_allow_empty(event):
    """Passing None with allow_empty_address=True creates a mail with no
    recipient — useful for mails that only get recipients later."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(None, event=event, allow_empty_address=True)

    assert mail.to is None
    assert mail.pk is not None


@pytest.mark.parametrize("user", (None, 42))
@pytest.mark.django_db
def test_to_mail_invalid_user_type_raises(event, user):
    """to_mail raises TypeError for non-string, non-User arguments."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    with pytest.raises(TypeError, match="must be a string or a User"):
        template.to_mail(user, event=event)


@pytest.mark.parametrize(
    ("subject_length", "expected_length", "truncated"),
    ((200, 200, False), (250, 199, True)),
)
@pytest.mark.django_db
def test_to_mail_subject_truncation_at_200_chars(
    event, subject_length, expected_length, truncated
):
    """Subjects over 200 characters are truncated with an ellipsis;
    subjects at exactly 200 characters are left unchanged."""
    subject = "A" * subject_length
    template = MailTemplateFactory(event=event, subject=subject, text="Body")
    mail = template.to_mail("test@example.com", event=event)

    assert len(mail.subject) == expected_length
    if truncated:
        assert mail.subject.endswith("\u2026")
    else:
        assert mail.subject == subject


@pytest.mark.django_db
def test_to_mail_substitutes_context_placeholders(event):
    """Placeholders in subject and text are replaced from the context."""
    template = MailTemplateFactory(
        event=event,
        subject="Welcome to {event_name}",
        text="Hi, {event_name} is great!",
    )
    mail = template.to_mail("test@example.com", event=event)
    assert mail.subject == f"Welcome to {event.name}"
    assert mail.text == f"Hi, {event.name} is great!"


@pytest.mark.django_db
def test_to_mail_missing_placeholder_raises(event):
    """A placeholder that isn't available in the context raises
    SendMailException so the organiser gets a useful error."""
    template = MailTemplateFactory(
        event=event, subject="Hello {nonexistent_placeholder}", text="Body"
    )
    with pytest.raises(SendMailException, match="KeyError"):
        template.to_mail("test@example.com", event=event)


@pytest.mark.django_db
def test_to_mail_commit_false_returns_unsaved(event):
    """With commit=False, the returned QueuedMail is not persisted."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event, commit=False)

    assert mail.pk is None
    assert mail.to == "test@example.com"


@pytest.mark.django_db
def test_to_mail_commit_false_with_user_uses_email_as_to(event):
    """With commit=False and a User, the user's email goes into the 'to'
    field instead of the M2M (since we can't save M2M without a pk)."""
    user = UserFactory()
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event, commit=False)

    assert mail.pk is None
    assert mail.to == user.email


@pytest.mark.django_db
def test_to_mail_preserves_reply_to_and_bcc(event):
    template = MailTemplateFactory(
        event=event,
        subject="Hi",
        text="Body",
        reply_to="reply@example.com",
        bcc="bcc@example.com",
    )
    mail = template.to_mail("test@example.com", event=event)
    assert mail.reply_to == "reply@example.com"
    assert mail.bcc == "bcc@example.com"


@pytest.mark.django_db
def test_to_mail_sets_template_reference(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event)
    assert mail.template == template


@pytest.mark.django_db
def test_to_mail_preserves_attachments(event):
    """The attachments parameter is passed through to the created QueuedMail."""
    attachments = [{"name": "file.pdf", "content": "base64data"}]
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event, attachments=attachments)
    assert mail.attachments == attachments


@pytest.mark.django_db
def test_to_mail_uses_template_event_when_none_passed(event):
    """When event=None, the template's own event is used."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=None)
    assert mail.event == event


@pytest.mark.django_db
def test_to_mail_links_explicit_submissions(event):
    """Explicit submissions are linked to the created mail."""
    submission = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = template.to_mail(
            "test@pretalx.org", event=event, submissions=[submission]
        )
        assert list(mail.submissions.all()) == [submission]


@pytest.mark.django_db
def test_to_mail_links_submission_from_context_kwargs(event):
    """A submission passed via context_kwargs is also linked to the mail."""
    submission = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = template.to_mail(
            "test@pretalx.org", event=event, context_kwargs={"submission": submission}
        )
        assert list(mail.submissions.all()) == [submission]


@pytest.mark.django_db
def test_to_mail_merges_submissions_and_context_kwargs_submission(event):
    """Submissions passed via both the submissions parameter and
    context_kwargs['submission'] are merged (deduplicated via set)."""
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = template.to_mail(
            "test@pretalx.org",
            event=event,
            submissions=[sub1],
            context_kwargs={"submission": sub2},
        )
        assert set(mail.submissions.all()) == {sub1, sub2}


@pytest.mark.django_db
def test_to_mail_skip_queue_sends_immediately(event):
    """With skip_queue=True, the mail is sent immediately after creation."""
    djmail.outbox = []
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    mail = template.to_mail("test@pretalx.org", event=event, skip_queue=True)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert sent_email.to == ["test@pretalx.org"]
    assert sent_email.subject == "Hi"


@pytest.mark.django_db
def test_mail_template_valid_placeholders_without_role(event):
    """A template with no role (custom template) returns the full set
    of placeholders for all kwargs (event, user, submission, slot)."""
    template = MailTemplateFactory(event=event, role=None)

    placeholders = template.valid_placeholders

    assert "event_name" in placeholders
    assert "proposal_title" in placeholders


@pytest.mark.parametrize(
    ("role", "expected_placeholders"),
    (
        (MailTemplateRoles.QUESTION_REMINDER, {"questions", "url"}),
        (MailTemplateRoles.NEW_SPEAKER_INVITE, {"invitation_link"}),
        (MailTemplateRoles.NEW_SUBMISSION_INTERNAL, {"orga_url"}),
    ),
)
@pytest.mark.django_db
def test_mail_template_valid_placeholders_includes_role_specific(
    event, role, expected_placeholders
):
    """Role-specific templates include their special placeholders on top
    of the standard ones."""
    with scopes_disabled():
        template = MailTemplate.objects.get(event=event, role=role)

    placeholders = template.valid_placeholders

    for expected in expected_placeholders:
        assert expected in placeholders


@pytest.mark.django_db
def test_queued_mail_str_contains_to_subject_state():
    mail = QueuedMailFactory(to="test@example.com", subject="Hello")
    result = str(mail)
    assert "test@example.com" in result
    assert "Hello" in result
    assert "draft" in result


@pytest.mark.parametrize(
    ("state", "error_data", "expected"),
    (
        (QueuedMailStates.DRAFT, {"error": "Connection refused"}, True),
        (QueuedMailStates.DRAFT, None, False),
        (QueuedMailStates.SENT, {"error": "stale"}, False),
    ),
)
@pytest.mark.django_db
def test_queued_mail_has_error_requires_draft_and_error_data(
    state, error_data, expected
):
    """has_error is True only for DRAFT mails with non-null error_data."""
    mail = QueuedMailFactory(state=state, error_data=error_data)
    assert mail.has_error is expected


@pytest.mark.django_db
def test_queued_mail_mark_sent_updates_state_and_timestamp():
    mail = QueuedMailFactory(
        state=QueuedMailStates.SENDING,
        error_data={"error": "previous"},
        error_timestamp="2024-01-01T00:00:00Z",
    )

    mail.mark_sent()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert mail.error_data is None
    assert mail.error_timestamp is None


@pytest.mark.django_db
def test_queued_mail_mark_failed_stores_error():
    mail = QueuedMailFactory(state=QueuedMailStates.SENDING)

    mail.mark_failed(ConnectionError("Connection refused"))
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "ConnectionError"
    assert "Connection refused" in mail.error_data["error"]
    assert mail.error_timestamp is not None


@pytest.mark.parametrize(
    ("smtp_code", "smtp_error", "expected_error_str"),
    (
        (550, b"Mailbox not found", "Mailbox not found"),
        (451, b"Temporary failure", "Temporary failure"),
        (550, "Already a string", "Already a string"),
    ),
)
@pytest.mark.django_db
def test_queued_mail_mark_failed_with_smtp_exception(
    smtp_code, smtp_error, expected_error_str
):
    """SMTPResponseException errors store the SMTP status code and
    decode byte error messages to UTF-8."""
    mail = QueuedMailFactory(state=QueuedMailStates.SENDING)
    exc = smtplib.SMTPResponseException(smtp_code, smtp_error)

    mail.mark_failed(exc)
    mail.refresh_from_db()

    assert mail.error_data["smtp_code"] == smtp_code
    assert mail.error_data["error"] == expected_error_str


def test_queued_mail_make_text_without_event_returns_plain_text():
    """Mails without an event (e.g. password resets) return just the text."""
    mail = QueuedMail(text="Hello there", subject="Hi")
    assert mail.make_text() == "Hello there"


@pytest.mark.parametrize(
    ("signature", "text", "expected"),
    (
        ("", "Hello there", "Hello there"),
        ("Best regards", "Hello there", "Hello there\n-- \nBest regards"),
        ("-- \nBest regards", "Hello there", "Hello there\n-- \nBest regards"),
    ),
)
@pytest.mark.django_db
def test_queued_mail_make_text_appends_signature(event, signature, text, expected):
    """Signatures are appended with a delimiter; existing delimiters
    aren't doubled; empty signatures leave the text unchanged."""
    if signature:
        event.mail_settings["signature"] = signature
    mail = QueuedMailFactory(event=event, text=text)
    assert mail.make_text() == expected


@pytest.mark.django_db
def test_queued_mail_make_html_renders_markdown(event):
    mail = QueuedMailFactory(event=event, text="Hello **world**")
    html = mail.make_html()

    assert "<strong>world</strong>" in html


def test_queued_mail_make_html_without_event():
    mail = QueuedMail(text="Hello world", subject="Hi", locale="en")
    html = mail.make_html()
    assert "Hello world" in html


@pytest.mark.django_db
def test_queued_mail_make_html_strips_signature_delimiter(event):
    """When the event signature starts with '-- ', make_html strips the
    delimiter prefix and includes the remaining signature text."""
    event.mail_settings["signature"] = "-- \nBest regards"
    mail = QueuedMailFactory(event=event, text="Hello")

    html = mail.make_html()

    assert "Best regards" in html


def test_queued_mail_prefixed_subject_without_event():
    mail = QueuedMail(subject="Hello", text="Body")
    assert mail.prefixed_subject == "Hello"


@pytest.mark.django_db
def test_queued_mail_prefixed_subject_with_event_prefix(event):
    event.mail_settings["subject_prefix"] = "TestConf"
    mail = QueuedMailFactory(event=event, subject="Hello")
    assert mail.prefixed_subject == "[TestConf] Hello"


@pytest.mark.parametrize("state", (QueuedMailStates.SENT, QueuedMailStates.SENDING))
@pytest.mark.django_db
def test_queued_mail_send_non_draft_raises(event, state):
    """Sending a mail that's already SENT or SENDING raises ValidationError."""
    mail = QueuedMailFactory(event=event, state=state, to="a@b.com")
    with pytest.raises(ValidationError):
        mail.send()


@pytest.mark.django_db
def test_queued_mail_send_delivers_email(event):
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


@pytest.mark.django_db
def test_queued_mail_send_non_persisted_delivers_email(event):
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


@pytest.mark.django_db
def test_queued_mail_send_without_event_delivers_email():
    """A persisted mail without an event skips the pre_send signal but
    still dispatches the celery task."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=None, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_queued_mail_send_skips_dispatch_when_signal_sets_sent(
    event, register_signal_handler
):
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


@pytest.mark.django_db
def test_queued_mail_send_broker_failure_marks_failed(event, monkeypatch):
    """When the celery broker is unreachable (OSError), the mail is marked
    as failed rather than crashing."""

    def broken_broker(**kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(common_mail.mail_send_task, "apply_async", broken_broker)
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Broker unavailable" in mail.error_data["error"]


@pytest.mark.django_db
def test_queued_mail_send_after_failure_clears_error(event):
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


@pytest.mark.django_db
def test_queued_mail_send_with_comma_separated_to(event):
    """When the 'to' field contains comma-separated addresses, all of them
    receive the email."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="a@example.com,b@example.com")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
    assert set(djmail.outbox[0].to) == {"a@example.com", "b@example.com"}


@pytest.mark.django_db
def test_queued_mail_copy_to_draft_creates_new_draft(event):
    original = QueuedMailFactory(
        event=event,
        state=QueuedMailStates.SENT,
        subject="Original",
        text="Original text",
        to="recipient@example.com",
        error_data={"error": "stale"},
    )

    copy = original.copy_to_draft()

    assert copy.pk != original.pk
    assert copy.state == QueuedMailStates.DRAFT
    assert copy.sent is None
    assert copy.error_data is None
    assert copy.error_timestamp is None
    assert copy.subject == "Original"
    assert copy.text == "Original text"
    assert copy.to == "recipient@example.com"


@pytest.mark.django_db
def test_queued_mail_copy_to_draft_preserves_to_users(event):
    user = UserFactory()
    original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    original.to_users.add(user)

    copy = original.copy_to_draft()
    assert list(copy.to_users.all()) == [user]


@pytest.mark.django_db
def test_queued_mail_prefetch_users_avoids_extra_queries(
    event, django_assert_num_queries
):
    """prefetch_users eagerly loads to_users so accessing them needs no
    additional queries."""
    user = UserFactory()
    mail = QueuedMailFactory(event=event)
    mail.to_users.add(user)

    with scope(event=event):
        mails = list(QueuedMail.objects.prefetch_users(event))

    # Accessing to_users should not trigger any queries thanks to prefetching
    with django_assert_num_queries(0):
        users = list(mails[0].to_users.all())
    assert users == [user]


@pytest.mark.parametrize(
    ("state", "error_data", "expected_computed_state"),
    (
        (QueuedMailStates.DRAFT, {"error": "oops"}, "failed"),
        (QueuedMailStates.DRAFT, None, "draft"),
        (QueuedMailStates.SENT, None, "sent"),
        (QueuedMailStates.SENDING, None, "sending"),
    ),
)
@pytest.mark.django_db
def test_queued_mail_with_computed_state_annotates_correctly(
    event, state, error_data, expected_computed_state
):
    mail = QueuedMailFactory(event=event, state=state, error_data=error_data)
    with scope(event=event):
        result = QueuedMail.objects.with_computed_state().get(pk=mail.pk)
    assert result.computed_state == expected_computed_state
