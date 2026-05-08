# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re

import pytest
from django.core import mail as djmail
from django.utils.safestring import SafeString, mark_safe
from django_scopes import scope

from pretalx.common.exceptions import SendMailException
from pretalx.common.text.formatting import FormattedString
from pretalx.mail.domain.queue import save_draft
from pretalx.mail.domain.render import (
    assert_rendered,
    build_trusted_mail,
    delivery_html,
    delivery_text,
    get_prefixed_subject,
    render_template_to_mail,
    render_to_mail,
)
from pretalx.mail.domain.send import send_draft, send_transient
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
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


def test_render_returns_unsaved_mail_with_no_recipient(event):
    """The renderer never sets mail.to or mail.to_users; recipient
    assignment is the caller's job (via save_draft or direct attribute)."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template)

    assert mail.to is None
    assert mail.subject == "Hi"
    assert mail.text == "Body"
    assert mail.pk is None


def test_save_draft_sets_to_address(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template)
    save_draft(mail, to="a@example.com")

    assert mail.pk is not None
    assert mail.to == "a@example.com"


def test_save_draft_attaches_to_users_and_submissions(event):
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    with scope(event=event):
        mail = render_template_to_mail(template)
        save_draft(mail, to_users=[user], submissions=[submission])

        assert mail.pk is not None
        assert list(mail.to_users.all()) == [user]
        assert list(mail.submissions.all()) == [submission]


def test_render_uses_explicit_locale(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template, locale="de")
    assert mail.locale == "de"


@pytest.mark.parametrize(
    ("subject_length", "expected_length", "truncated"),
    ((200, 200, False), (250, 199, True)),
)
def test_render_subject_truncation_at_200_chars(
    event, subject_length, expected_length, truncated
):
    """Subjects over 200 characters are truncated with an ellipsis;
    subjects at exactly 200 characters are left unchanged."""
    subject = "A" * subject_length
    template = MailTemplateFactory(event=event, subject=subject, text="Body")
    mail = render_template_to_mail(template)

    assert len(mail.subject) == expected_length
    if truncated:
        assert mail.subject.endswith("…")
    else:
        assert mail.subject == subject


def test_render_substitutes_context_placeholders(event):
    template = MailTemplateFactory(
        event=event,
        subject="Welcome to {event_name}",
        text="Hi, {event_name} is great!",
    )
    mail = render_template_to_mail(template)
    assert mail.subject == f"Welcome to {event.name}"
    assert mail.text == f"Hi, {event.name} is great!"


def test_render_missing_placeholder_raises(event):
    """A placeholder that isn't available in the context raises
    SendMailException so the organiser gets a useful error."""
    template = MailTemplateFactory(
        event=event, subject="Hello {nonexistent_placeholder}", text="Body"
    )
    with pytest.raises(SendMailException, match="KeyError"):
        render_template_to_mail(template)


def test_render_preserves_reply_to_and_bcc(event):
    template = MailTemplateFactory(
        event=event,
        subject="Hi",
        text="Body",
        reply_to="reply@example.com",
        bcc="bcc@example.com",
    )
    mail = render_template_to_mail(template)
    assert mail.reply_to == "reply@example.com"
    assert mail.bcc == "bcc@example.com"


def test_render_sets_template_reference(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template)
    assert mail.template == template


def test_render_uses_template_event(event):
    """The mail's event is taken from ``template.event``."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    mail = render_template_to_mail(template)
    assert mail.event == event


def test_render_then_save_draft_send_draft_sends_immediately(event):
    djmail.outbox = []
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")

    mail = render_template_to_mail(template)
    save_draft(mail, to="test@pretalx.org")
    send_draft(mail)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert sent_email.to == ["test@pretalx.org"]
    assert sent_email.subject == "Hi"


def test_render_template_to_mail_rejects_unsaved_template(event):
    """Unsaved templates have no canonical event-FK, no role binding,
    and no DB identity to attach to the resulting QueuedMail. The
    raw-string path :func:`render_to_mail` is the right tool there."""
    from pretalx.mail.models import MailTemplate as MailTemplateModel  # noqa: PLC0415

    template = MailTemplateModel(event=event, subject="Hi", text="Body")
    with pytest.raises(ValueError, match="requires a saved MailTemplate"):
        render_template_to_mail(template)


def test_render_to_mail_renders_raw_strings(event):
    # The reset_password / invitation shape: ad-hoc subject/text,
    # bound to an event for placeholder context.
    user = UserFactory(name="Jane Doe")
    mail = render_to_mail(
        subject_template="Welcome to {event_name}",
        text_template="Hi {name}, welcome to {event_name}!",
        event=event,
        locale=user.locale,
        context_kwargs={"user": user},
    )

    assert mail.subject == f"Welcome to {event.name}"
    assert "Jane Doe" in mail.text
    assert mail.text_html is not None
    assert mail.template is None
    assert mail.event == event


def test_render_to_mail_send_transient_sends_immediately(event):
    djmail.outbox = []
    mail = render_to_mail(subject_template="Test", text_template="Body", event=event)
    mail.to = "test@example.com"
    send_transient(mail)

    assert mail.pk is None
    assert len(djmail.outbox) == 1


def test_render_to_mail_without_event():
    user = UserFactory(name="Admin")
    mail = render_to_mail(
        subject_template="Reset",
        text_template="Hi {name}",
        locale=user.locale,
        context_kwargs={"user": user},
    )

    assert "Admin" in mail.text
    assert mail.event is None


def test_delivery_text_without_event_returns_plain_text():
    """Mails without an event (e.g. password resets) return just the text."""
    mail = QueuedMail(text="Hello there", subject="Hi")
    assert delivery_text(mail) == "Hello there"


@pytest.mark.parametrize(
    ("signature", "text", "expected"),
    (
        ("", "Hello there", "Hello there"),
        ("Best regards", "Hello there", "Hello there\n-- \nBest regards"),
        ("-- \nBest regards", "Hello there", "Hello there\n-- \nBest regards"),
    ),
)
def test_delivery_text_appends_signature(event, signature, text, expected):
    """Signatures are appended with a delimiter; existing delimiters
    aren't doubled; empty signatures leave the text unchanged."""
    if signature:
        event.mail_settings["signature"] = signature
    mail = QueuedMailFactory(event=event, text=text)
    assert delivery_text(mail) == expected


def test_delivery_html_renders_markdown(event):
    mail = QueuedMailFactory(event=event, text="Hello **world**")
    html = delivery_html(mail)

    assert "<strong>world</strong>" in html


def test_delivery_html_without_event():
    mail = QueuedMail(text="Hello world", subject="Hi", locale="en")
    html = delivery_html(mail)
    assert "Hello world" in html


def test_delivery_html_prefers_text_html_when_set(event):
    # If text_html is set (placeholder pipeline), delivery_html uses it
    # directly; otherwise it falls back to rendering self.text.
    mail = QueuedMailFactory(
        event=event, text="plain form raw <br>", text_html="html form raw &lt;br&gt;"
    )

    html = delivery_html(mail)

    assert "&lt;br&gt;" in html
    assert "plain form raw" not in html


def test_delivery_html_legacy_fallback_when_text_html_is_none(event):
    mail = QueuedMailFactory(event=event, text="hello", text_html=None)
    html = delivery_html(mail)
    assert "hello" in html


def test_delivery_html_strips_signature_delimiter(event):
    """When the event signature starts with '-- ', delivery_html strips the
    delimiter prefix and includes the remaining signature text."""
    event.mail_settings["signature"] = "-- \nBest regards"
    mail = QueuedMailFactory(event=event, text="Hello")

    html = delivery_html(mail)

    assert "Best regards" in html


def test_render_escapes_malicious_user_name_in_html_body(event):
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

    mail = render_template_to_mail(template, context_kwargs={"user": user})

    assert payload not in mail.text
    assert "<br>" not in mail.text
    assert '<a href="https://phish.com"' not in mail.text
    assert "We have detected suspicious activity" in mail.text
    assert payload not in mail.text_html
    assert "<span>" in mail.text_html
    assert "&lt;a href=" in mail.text_html
    rendered_html = delivery_html(mail)
    assert '<a href="https://phish.com"' not in rendered_html
    assert "&lt;a href=" in rendered_html


def test_render_blocks_bare_url_autolink_inside_user_name(event):
    # The <span> fence puts user content in MAIL_BODY_CLEANER's
    # skip_tags; organiser-typed URLs outside the fence still autolink.
    user = UserFactory(name="Visit https://phish.com now")
    template = MailTemplateFactory(
        event=event,
        subject="Hi",
        text="Hi {name} — also check https://example.com today!",
    )

    mail = render_template_to_mail(template, context_kwargs={"user": user})

    rendered_html = delivery_html(mail)
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
def test_render_blocks_injection_via_submission_title(event, payload):
    submission = SubmissionFactory(event=event, title=payload)
    template = MailTemplateFactory(
        event=event,
        subject="About {proposal_title}",
        text="About {proposal_title}. Please respond.",
    )

    with scope(event=event):
        mail = render_template_to_mail(
            template, context_kwargs={"submission": submission}
        )

    _assert_no_phish_in_rendered(delivery_html(mail))
    mail.text_html = None
    _assert_no_phish_in_rendered(delivery_html(mail), allow_bare_url_autolink=True)


@pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
def test_render_blocks_injection_via_speaker_name(event, payload):
    speaker_profile = SpeakerFactory(event=event, user__name=payload)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        submission.speakers.add(speaker_profile)
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Speakers: {speakers} — welcome!"
    )

    with scope(event=event):
        mail = render_template_to_mail(
            template, context_kwargs={"submission": submission}
        )

    _assert_no_phish_in_rendered(delivery_html(mail))
    mail.text_html = None
    _assert_no_phish_in_rendered(delivery_html(mail), allow_bare_url_autolink=True)


def test_render_preserves_markdown_formatting_around_escaped_placeholder(event):
    user = UserFactory(name="<b>Jane</b>")
    template = MailTemplateFactory(event=event, subject="Hi", text="**Hello** {name}!")

    mail = render_template_to_mail(template, context_kwargs={"user": user})

    rendered_html = delivery_html(mail)
    assert "<strong>Hello</strong>" in rendered_html
    assert "<b>Jane</b>" not in rendered_html
    assert "&lt;b&gt;Jane&lt;/b&gt;" in rendered_html


def test_render_url_placeholder_survives_html_render(event):
    # LinkMailTextPlaceholder produces a SafeString HTML variant so ``&``
    # in URLs is not corrupted to ``&amp;`` before the linkifier runs.
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Visit {event_url} for details."
    )

    mail = render_template_to_mail(template)

    assert event.urls.base.full() in mail.text
    rendered_html = delivery_html(mail)
    assert event.urls.base.full() in rendered_html


def test_assert_rendered_accepts_formatted_and_safe_strings():
    assert_rendered(
        FormattedString("subject"), FormattedString("text"), SafeString("html")
    )
    assert_rendered(mark_safe("subject"), mark_safe("text"), mark_safe("html"))


def test_assert_rendered_accepts_none_text_html():
    """text_html=None is the natural state on the trusted-mail path
    and on organiser-edited drafts: the markdown render is deferred
    to send time."""
    assert_rendered(FormattedString("subject"), FormattedString("text"), None)


def test_assert_rendered_rejects_raw_str_text_html():
    with pytest.raises(TypeError, match="Mail text_html must be"):
        assert_rendered(FormattedString("subject"), FormattedString("text"), "raw str")


def test_build_trusted_mail_marks_content_safe_and_constructs_unsaved(event):
    mail = build_trusted_mail(
        event=event, to="a@example.com", subject="Subject", text="Body"
    )
    assert mail.pk is None
    assert mail.event == event
    assert mail.to == "a@example.com"
    assert mail.subject == "Subject"
    assert mail.text == "Body"
    assert mail.text_html is None
    assert isinstance(mail.subject, SafeString)
    assert isinstance(mail.text, SafeString)


def test_build_trusted_mail_does_not_render_placeholders(event):
    """The trusted path is for organiser-final content; placeholders pass
    through verbatim. A caller that wants substitution must use
    :func:`render_template_to_mail`."""
    mail = build_trusted_mail(
        event=event,
        to="a@example.com",
        subject="Hi {event_name}",
        text="Welcome to {event_name}, {user_name}!",
    )
    assert mail.subject == "Hi {event_name}"
    assert mail.text == "Welcome to {event_name}, {user_name}!"


@pytest.mark.parametrize(
    ("position", "field"), ((0, "subject"), (1, "text"), (2, "text_html"))
)
def test_assert_rendered_rejects_raw_str(position, field):
    values = [FormattedString("subject"), FormattedString("text"), SafeString("html")]
    values[position] = "raw str"
    with pytest.raises(TypeError, match=f"Mail {field} must be"):
        assert_rendered(*values)
