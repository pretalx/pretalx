# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.template.loader import get_template
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import override

from pretalx.common.exceptions import SendMailException
from pretalx.common.templatetags.rich_text import (
    render_mail_body,
    render_markdown_abslinks,
)
from pretalx.common.text.formatting import (
    MODE_HTML,
    MODE_PLAIN,
    FormattedString,
    format_map,
)
from pretalx.mail.domain.context import get_mail_context
from pretalx.mail.models import QueuedMail


def assert_rendered(subject, text, text_html):
    """Construction-time guard: ``subject`` / ``text`` must be
    ``FormattedString`` (from :func:`format_map`) or ``SafeString``
    (from :func:`mark_safe`); ``text_html`` may also be ``None``. Markers
    do not survive the DB round-trip, so the persisted send path
    (``send_draft``) cannot re-validate."""
    for name, value, accept_none in (
        ("subject", subject, False),
        ("text", text, False),
        ("text_html", text_html, True),
    ):
        if accept_none and value is None:
            continue
        if not isinstance(value, (FormattedString, SafeString)):
            optional = " or None" if accept_none else ""
            raise TypeError(
                f"Mail {name} must be a FormattedString or SafeString{optional}, "
                f"got {type(value).__name__}."
            )


def get_prefixed_subject(event, subject):
    if not (prefix := event.mail_settings["subject_prefix"]):
        return subject
    if not (prefix.startswith("[") and prefix.endswith("]")):
        prefix = f"[{prefix}]"
    if subject.startswith(prefix):
        return subject
    return f"{prefix} {subject}"


def render_to_mail(
    *,
    subject_template,
    text_template,
    event=None,
    locale=None,
    safe_extra_context=None,
    context_kwargs=None,
):
    """Render raw subject/text strings against the placeholder context
    and return an unsaved :class:`QueuedMail`. Use this for ad-hoc
    content (system mails, on-the-fly invitations); for organiser-managed
    :class:`MailTemplate`s, prefer :func:`render_template_to_mail`.

    ``event`` may be ``None`` for global system mails (password resets,
    organiser team invites). If set, it is injected into the context.

    Recipient and envelope fields (``to``, ``reply_to``, ``bcc``,
    ``template``) are not rendering inputs and are left for the caller
    to set on the returned mail before persisting or dispatching.
    """
    context_kwargs = {**(context_kwargs or {}), "event": event}
    with override(locale):
        context = get_mail_context(
            safe_extra_context=safe_extra_context, **context_kwargs
        )
        try:
            subject = format_map(subject_template, context, mode=MODE_PLAIN)
            text = format_map(text_template, context, mode=MODE_PLAIN)
            text_html = render_mail_body(
                format_map(text_template, context, mode=MODE_HTML)
            )
        except KeyError as e:
            raise SendMailException(
                f"Experienced KeyError when rendering email text: {e!s}"
            ) from e

        if len(subject) > 200:
            subject = FormattedString(subject[:198] + "…")

        return QueuedMail(
            event=event, subject=subject, text=text, text_html=text_html, locale=locale
        )


def build_trusted_mail(*, event, to, subject, text):
    """Unsaved :class:`QueuedMail` from organiser-final content. No
    placeholder rendering — the caller asserts the strings are trusted.
    Markdown rendering of the body happens at send time via
    :func:`delivery_html_body`'s fallback."""
    return QueuedMail(
        event=event,
        to=to,
        subject=mark_safe(subject),  # noqa: S308 -- organiser-final content
        text=mark_safe(text),  # noqa: S308 -- organiser-final content
    )


def render_template_to_mail(
    template, *, locale=None, safe_extra_context=None, context_kwargs=None
):
    """The canonical, safe way to construct QueuedMail objects from a
    persisted :class:`MailTemplate`. Returns an unsaved
    :class:`QueuedMail` with ``to`` / ``to_users`` unset; the caller picks
    :func:`~pretalx.mail.domain.queue.save_draft`,
    :func:`~pretalx.mail.domain.send.send_draft`, or
    :func:`~pretalx.mail.domain.send.send_transient` next.

    For ad-hoc content not backed by a saved template (system mails,
    on-the-fly invitations), use :func:`render_to_mail` directly.
    """
    if template._state.adding:
        raise ValueError(
            "render_template_to_mail requires a saved MailTemplate; "
            "use render_to_mail for ad-hoc subject/text strings."
        )
    mail = render_to_mail(
        subject_template=template.subject,
        text_template=template.text,
        event=template.event,
        locale=locale,
        safe_extra_context=safe_extra_context,
        context_kwargs=context_kwargs,
    )
    mail.template = template
    mail.reply_to = template.reply_to
    mail.bcc = template.bcc
    return mail


def delivery_html_body(mail):
    """Return the sanitised HTML body of ``mail`` — the same markup the
    recipient will see, without the outer mail-wrapper layout. The
    inner part of :func:`delivery_html`; also used directly by the
    organiser outbox / mail-log preview views, so the preview matches
    the delivered body byte-for-byte."""
    if mail.text_html is not None:
        # Already rendered at render_template_to_mail time (markdown +
        # bleach via render_mail_body, with user-controlled substitutions
        # escaped and wrapped in <span>/<div>). Stored in the DB as a
        # plain string; re-mark safe for template rendering.
        return mark_safe(mail.text_html)  # noqa: S308  -- rendered via render_mail_body at creation
    # No placeholder-rendered HTML available — the mail was constructed
    # directly (literal string) or the organiser edited the draft body
    # after rendering (see ``MailDetailForm.save``). Fall back to the
    # legacy markdown/bleach pipeline, which autolinks bare URLs in
    # organiser-typed text as before. This path is safe only for text
    # that is fully organiser- or system-controlled; user-content
    # placeholders are already pre-sanitised in their plain variant so
    # they cannot re-inject HTML or markdown links when this fallback
    # runs.
    return render_markdown_abslinks(mail.text)


def delivery_html(mail):
    """Build the full HTML payload of ``mail`` for SMTP delivery: the
    body (via :func:`delivery_html_body`) wrapped in the styled email
    layout."""
    event = mail.event
    sig = None
    if event:
        sig = event.mail_settings["signature"]
        if sig.strip().startswith("-- "):
            sig = sig.strip()[3:].strip()
    html_context = {
        "body": delivery_html_body(mail),
        "event": event,
        "color": (event.primary_color if event else "")
        or settings.DEFAULT_EVENT_PRIMARY_COLOR,
        "locale": mail.locale,
        "rtl": mail.locale in settings.LANGUAGES_BIDI,
        "subject": mail.subject,
        "signature": sig,
    }
    return get_template("mail/mailwrapper.html").render(html_context)


def delivery_text(mail):
    """Build the full plain-text payload of ``mail`` for SMTP delivery:
    the text body with the event signature appended."""
    event = mail.event
    if not event or not event.mail_settings["signature"]:
        return mail.text
    sig = event.mail_settings["signature"]
    if not sig.strip().startswith("-- "):
        sig = f"-- \n{sig}"
    return f"{mail.text}\n{sig}"
