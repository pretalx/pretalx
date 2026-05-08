# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re

import pytest
from django.core import mail as djmail
from django_scopes import scope

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.render import (
    get_prefixed_subject,
    make_html,
    make_text,
    render_template_to_mail,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import MailTemplate, QueuedMail
from tests.factories import (
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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
def test_get_prefixed_subject_adds_brackets(event, prefix, subject, expected):
    """Subjects are prefixed with brackets; already-bracketed prefixes
    aren't double-wrapped; already-prefixed subjects aren't duplicated."""
    event.mail_settings["subject_prefix"] = prefix
    assert get_prefixed_subject(event, subject) == expected


def test_to_mail_with_email_string(event):
    """When user is a string, it's used as the 'to' address."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event)

    assert mail.to == "test@example.com"
    assert mail.subject == "Hi"
    assert mail.text == "Body"
    assert mail.pk is not None


def test_to_mail_with_user_object(event):
    """When user is a User instance, it's added via the to_users M2M."""
    user = UserFactory()
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event)

    assert mail.to is None
    assert mail.pk is not None
    assert list(mail.to_users.all()) == [user]


def test_to_mail_uses_user_locale(event):
    user = UserFactory(locale="de")
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event)
    assert mail.locale == "de"


def test_to_mail_explicit_locale_overrides_user(event):
    user = UserFactory(locale="de")
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event, locale="fr")
    assert mail.locale == "fr"


def test_to_mail_allows_none_user_with_allow_empty(event):
    """Passing None with allow_empty_address=True creates a mail with no
    recipient — useful for mails that only get recipients later."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(None, event=event, allow_empty_address=True)

    assert mail.to is None
    assert mail.pk is not None


@pytest.mark.parametrize("user", (None, 42))
def test_to_mail_invalid_user_type_raises(event, user):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    with pytest.raises(TypeError, match="must be a string or a User"):
        template.to_mail(user, event=event)


@pytest.mark.parametrize(
    ("subject_length", "expected_length", "truncated"),
    ((200, 200, False), (250, 199, True)),
)
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
        assert mail.subject.endswith("…")
    else:
        assert mail.subject == subject


def test_to_mail_substitutes_context_placeholders(event):
    template = MailTemplateFactory(
        event=event,
        subject="Welcome to {event_name}",
        text="Hi, {event_name} is great!",
    )
    mail = template.to_mail("test@example.com", event=event)
    assert mail.subject == f"Welcome to {event.name}"
    assert mail.text == f"Hi, {event.name} is great!"


def test_to_mail_missing_placeholder_raises(event):
    """A placeholder that isn't available in the context raises
    SendMailException so the organiser gets a useful error."""
    template = MailTemplateFactory(
        event=event, subject="Hello {nonexistent_placeholder}", text="Body"
    )
    with pytest.raises(SendMailException, match="KeyError"):
        template.to_mail("test@example.com", event=event)


def test_to_mail_commit_false_returns_unsaved(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event, commit=False)

    assert mail.pk is None
    assert mail.to == "test@example.com"


def test_to_mail_commit_false_with_user_uses_email_as_to(event):
    """With commit=False and a User, the user's email goes into the 'to'
    field instead of the M2M (since we can't save M2M without a pk)."""
    user = UserFactory()
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail(user, event=event, commit=False)

    assert mail.pk is None
    assert mail.to == user.email


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


def test_to_mail_sets_template_reference(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event)
    assert mail.template == template


def test_to_mail_preserves_attachments(event):
    attachments = [{"name": "file.pdf", "content": "base64data"}]
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=event, attachments=attachments)
    assert mail.attachments == attachments


def test_to_mail_uses_template_event_when_none_passed(event):
    """When event=None, the template's own event is used."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = template.to_mail("test@example.com", event=None)
    assert mail.event == event


def test_to_mail_links_explicit_submissions(event):
    submission = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = template.to_mail(
            "test@pretalx.org", event=event, submissions=[submission]
        )
        assert list(mail.submissions.all()) == [submission]


def test_to_mail_links_submission_from_context_kwargs(event):
    submission = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = template.to_mail(
            "test@pretalx.org", event=event, context_kwargs={"submission": submission}
        )
        assert list(mail.submissions.all()) == [submission]


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


def test_to_mail_skip_queue_sends_immediately(event):
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


def test_to_mail_on_unsaved_template(event):
    # Unsaved templates (no pk) back ad-hoc mails like password reset.
    template = MailTemplate(subject="Hi", text="Body text here")
    mail = template.to_mail("test@example.com", event=event, commit=False)

    assert mail.to == "test@example.com"
    assert mail.subject == "Hi"
    assert mail.text == "Body text here"
    assert mail.template is None


def test_to_mail_on_unsaved_template_with_placeholders(event):
    template = MailTemplate(
        subject="Welcome to {event_name}", text="Hi {name}, welcome to {event_name}!"
    )
    user = UserFactory(name="Jane Doe")
    mail = template.to_mail(
        user=user, event=event, context_kwargs={"user": user}, commit=False
    )

    assert mail.subject == f"Welcome to {event.name}"
    assert "Jane Doe" in mail.text
    assert mail.text_html is not None
    assert mail.template is None


def test_to_mail_on_unsaved_template_sends_immediately(event):
    # skip_queue + commit=False is the reset_password/change_password shape.
    djmail.outbox = []
    template = MailTemplate(subject="Test", text="Body")
    mail = template.to_mail(
        "test@example.com", event=event, commit=False, skip_queue=True
    )

    assert mail.pk is None
    assert len(djmail.outbox) == 1


def test_to_mail_on_unsaved_template_without_event():
    template = MailTemplate(subject="Reset", text="Hi {name}")
    user = UserFactory(name="Admin")
    mail = template.to_mail(
        user=user, event=None, context_kwargs={"user": user}, commit=False
    )

    assert "Admin" in mail.text
    assert mail.event is None


def test_render_template_to_mail_callable_directly(event):
    """The domain function works without going through the model thin
    method."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template, "test@example.com", event)
    assert mail.to == "test@example.com"
    assert mail.subject == "Hi"


def test_make_text_without_event_returns_plain_text():
    """Mails without an event (e.g. password resets) return just the text."""
    mail = QueuedMail(text="Hello there", subject="Hi")
    assert make_text(mail) == "Hello there"


@pytest.mark.parametrize(
    ("signature", "text", "expected"),
    (
        ("", "Hello there", "Hello there"),
        ("Best regards", "Hello there", "Hello there\n-- \nBest regards"),
        ("-- \nBest regards", "Hello there", "Hello there\n-- \nBest regards"),
    ),
)
def test_make_text_appends_signature(event, signature, text, expected):
    """Signatures are appended with a delimiter; existing delimiters
    aren't doubled; empty signatures leave the text unchanged."""
    if signature:
        event.mail_settings["signature"] = signature
    mail = QueuedMailFactory(event=event, text=text)
    assert make_text(mail) == expected


def test_make_html_renders_markdown(event):
    mail = QueuedMailFactory(event=event, text="Hello **world**")
    html = make_html(mail)

    assert "<strong>world</strong>" in html


def test_make_html_without_event():
    mail = QueuedMail(text="Hello world", subject="Hi", locale="en")
    html = make_html(mail)
    assert "Hello world" in html


def test_make_html_prefers_text_html_when_set(event):
    # If text_html is set (placeholder pipeline), make_html uses it
    # directly; otherwise it falls back to rendering self.text.
    mail = QueuedMailFactory(
        event=event, text="plain form raw <br>", text_html="html form raw &lt;br&gt;"
    )

    html = make_html(mail)

    assert "&lt;br&gt;" in html
    assert "plain form raw" not in html


def test_make_html_legacy_fallback_when_text_html_is_none(event):
    mail = QueuedMailFactory(event=event, text="hello", text_html=None)
    html = make_html(mail)
    assert "hello" in html


def test_make_html_strips_signature_delimiter(event):
    """When the event signature starts with '-- ', make_html strips the
    delimiter prefix and includes the remaining signature text."""
    event.mail_settings["signature"] = "-- \nBest regards"
    mail = QueuedMailFactory(event=event, text="Hello")

    html = make_html(mail)

    assert "Best regards" in html


def test_to_mail_escapes_malicious_user_name_in_html_body(event):
    # CVE regression: a malicious User.name must not surface as live
    # HTML. The plain body has tags stripped (so the edited-draft
    # fallback can't re-HTML-ify), the HTML body escapes inside a
    # <span> fence that defeats downstream autolinking.
    payload = (
        "user,<br>We have detected suspicious activity. "
        '<a href="https://phish.com">Click here to secure your account.</a a=">'
    )
    user = UserFactory(name=payload)
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Hi {name}, welcome!"
    )

    mail = template.to_mail(
        user=user, event=event, context_kwargs={"user": user}, commit=False
    )

    assert payload not in mail.text
    assert "<br>" not in mail.text
    assert '<a href="https://phish.com"' not in mail.text
    assert "We have detected suspicious activity" in mail.text
    assert payload not in mail.text_html
    assert "<span>" in mail.text_html
    assert "&lt;a href=" in mail.text_html
    rendered_html = make_html(mail)
    assert '<a href="https://phish.com"' not in rendered_html
    assert "&lt;a href=" in rendered_html


def test_to_mail_blocks_bare_url_autolink_inside_user_name(event):
    # The <span> fence puts user content in MAIL_BODY_CLEANER's
    # skip_tags; organiser-typed URLs outside the fence still autolink.
    user = UserFactory(name="Visit https://phish.com now")
    template = MailTemplateFactory(
        event=event,
        subject="Hi",
        text="Hi {name} — also check https://example.com today!",
    )

    mail = template.to_mail(
        user=user, event=event, context_kwargs={"user": user}, commit=False
    )

    rendered_html = make_html(mail)
    assert '<a href="https://phish.com"' not in rendered_html
    assert '<a href="https://example.com"' in rendered_html


_INJECTION_PAYLOADS = (
    pytest.param(
        'user,<br>Click <a href="https://phish.com">here</a a=">',
        id="html_a_tag_malformed",
    ),
    pytest.param("[Click here](https://phish.com)", id="markdown_link"),
    pytest.param("![img](https://phish.com)", id="markdown_image"),
    pytest.param("<script>alert(1)</script>", id="script_tag"),
    pytest.param(
        "Reference-style [label][1]\n\n[1]: https://phish.com",
        id="markdown_reference_link",
    ),
    # Blank lines break the <span> wrapper apart across the markdown
    # paragraph split; content after the first paragraph escapes the
    # autolinker skip_tags fence unless render_html collapses them.
    pytest.param("innocent\n\nhttps://phish.com\n\nhi", id="blank_line_bare_url"),
    pytest.param(
        "hi\n\n# Click here to reset your password https://phish.com",
        id="blank_line_heading_consume",
    ),
    # conditional_escape must encode <> before markdown, or <url>
    # becomes a live autolink.
    pytest.param("<https://phish.com>", id="angle_bracket_autolink"),
)


_PHISH_LINK_RE = re.compile(r'<a[^>]*href="https://phish\.com[^"]*"[^>]*>([^<]*)</a>')


def _assert_no_phish_in_rendered(
    rendered: str, *, allow_bare_url_autolink: bool = False
) -> None:
    # A bare URL autolink (visible label == href) can't mislead, so
    # it's tolerated on the edited-draft fallback path where user
    # content isn't inside the <span> fence.
    assert "<script" not in rendered
    assert '<img src="https://phish.com"' not in rendered
    assert '<img src="https://phish.com' not in rendered
    for match in _PHISH_LINK_RE.finditer(rendered):
        inner = match.group(1).strip()
        if allow_bare_url_autolink and inner == "https://phish.com":
            continue
        raise AssertionError(  # pragma: no cover
            f"Phish link with non-matching inner text: {match.group(0)!r}"
        )


# The parametrised integration tests below share one rule: the primary
# text_html path must have no phish <a> at all; the edited-draft
# fallback path may contain a bare-URL autolink but nothing misleading.


@pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
def test_to_mail_blocks_injection_via_submission_title(event, payload):
    submission = SubmissionFactory(event=event, title=payload)
    template = MailTemplateFactory(
        event=event,
        subject="About {proposal_title}",
        text="About {proposal_title}. Please respond.",
    )

    with scope(event=event):
        mail = template.to_mail(
            user="recipient@example.com",
            event=event,
            context_kwargs={"submission": submission},
            commit=False,
        )

    _assert_no_phish_in_rendered(make_html(mail))
    mail.text_html = None
    _assert_no_phish_in_rendered(make_html(mail), allow_bare_url_autolink=True)


@pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
def test_to_mail_blocks_injection_via_speaker_name(event, payload):
    speaker_profile = SpeakerFactory(event=event, user__name=payload)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        submission.speakers.add(speaker_profile)
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Speakers: {speakers} — welcome!"
    )

    with scope(event=event):
        mail = template.to_mail(
            user="recipient@example.com",
            event=event,
            context_kwargs={"submission": submission},
            commit=False,
        )

    _assert_no_phish_in_rendered(make_html(mail))
    mail.text_html = None
    _assert_no_phish_in_rendered(make_html(mail), allow_bare_url_autolink=True)


def test_to_mail_preserves_markdown_formatting_around_escaped_placeholder(event):
    user = UserFactory(name="<b>Jane</b>")
    template = MailTemplateFactory(event=event, subject="Hi", text="**Hello** {name}!")

    mail = template.to_mail(
        user=user, event=event, context_kwargs={"user": user}, commit=False
    )

    rendered_html = make_html(mail)
    assert "<strong>Hello</strong>" in rendered_html
    assert "<b>Jane</b>" not in rendered_html
    assert "&lt;b&gt;Jane&lt;/b&gt;" in rendered_html


def test_to_mail_url_placeholder_survives_html_render(event):
    # LinkMailTextPlaceholder produces a SafeString HTML variant so ``&``
    # in URLs is not corrupted to ``&amp;`` before the linkifier runs.
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Visit {event_url} for details."
    )

    mail = template.to_mail(user="a@b.test", event=event, commit=False)

    assert event.urls.base.full() in mail.text
    rendered_html = make_html(mail)
    assert event.urls.base.full() in rendered_html
