# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.utils.translation import override

from pretalx.common.exceptions import SendMailException
from pretalx.common.text.formatting import MODE_HTML, MODE_PLAIN, format_map
from pretalx.mail.domain.context import get_mail_context
from pretalx.mail.models import QueuedMail
from pretalx.person.models import User


def get_prefixed_subject(event, subject):
    if not (prefix := event.mail_settings["subject_prefix"]):
        return subject
    if not (prefix.startswith("[") and prefix.endswith("]")):
        prefix = f"[{prefix}]"
    if subject.startswith(prefix):
        return subject
    return f"{prefix} {subject}"


def render_template_to_mail(
    template,
    user,
    event,
    *,
    locale=None,
    safe_extra_context=None,
    context_kwargs=None,
    skip_queue=False,
    commit=True,
    allow_empty_address=False,
    submissions=None,
    attachments=False,
):
    """Render ``template`` against the given context and produce a
    ``QueuedMail``. This is the canonical and safe way of constructing
    emails, particularly emails including user-generated input (e.g.
    session titles, user names, etc).

    When the template is unsaved (``template.pk is None``), the resulting
    ``QueuedMail`` will have ``template=None``.

    :param user: Either a :class:`~pretalx.person.models.user.User` or an
        email address as a string.
    :param submissions: A list of submissions to which this email belongs.
        This is handled as an addition to any `submission` object present
        in ``context_kwargs``.
    :param event: The event to which this email belongs. May be ``None``.
    :param locale: The locale will be set via the event and the recipient,
        but can be overridden with this parameter.
    :param safe_extra_context: Per-call overrides for the template
        context. Every value must be a
        :class:`~django.utils.safestring.SafeString`, a
        :class:`~pretalx.common.text.formatting.EmailAlternativeString`,
        a :class:`~urlman.UrlString`, or a numeric type
        (``int``, ``float``, ``Decimal``); see
        :func:`~pretalx.mail.domain.context.get_mail_context`.
    :param context_kwargs: Passed to get_mail_context to retrieve the correct
        context when rendering the template.
    :param skip_queue: Send directly. If combined with commit=False, this will
        remove any logging and traces.
    :param commit: Set ``False`` to return an unsaved object.
    """
    from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- slow markdown import
        render_mail_body,
    )

    if isinstance(user, str):
        address = user
        users = None
    elif isinstance(user, User):
        address = None
        users = [user]
        locale = locale or user.locale
    elif not user and allow_empty_address:
        address = None
        users = None
    else:
        raise TypeError(
            "First argument to render_template_to_mail must be a string or a User, "
            "not " + str(type(user))
        )
    if users and not commit:
        address = ",".join(user.email for user in users)
        users = None
    event = event or getattr(template, "event", None)

    context_kwargs = {**(context_kwargs or {}), "event": event}
    with override(locale):
        context = get_mail_context(
            safe_extra_context=safe_extra_context, **context_kwargs
        )
        try:
            subject = format_map(template.subject, context, mode=MODE_PLAIN)
            text = format_map(template.text, context, mode=MODE_PLAIN)
            text_html = render_mail_body(
                format_map(template.text, context, mode=MODE_HTML)
            )
        except KeyError as e:
            raise SendMailException(
                f"Experienced KeyError when rendering email text: {e!s}"
            ) from e

        if len(subject) > 200:
            subject = subject[:198] + "…"

        mail = QueuedMail(
            event=event,
            template=template if template.pk else None,
            to=address,
            reply_to=template.reply_to,
            bcc=template.bcc,
            subject=subject,
            text=text,
            text_html=text_html,
            locale=locale,
            attachments=attachments,
        )
        if commit:
            mail.save()
            submissions = set(submissions or [])
            if submission := context_kwargs.get("submission"):
                submissions.add(submission)
            if submissions:
                mail.submissions.set(submissions)
            if users:
                mail.to_users.set(users)
        if skip_queue:
            mail.send()
    return mail


def render_html_body(mail):
    """Return the sanitised HTML body of ``mail`` — the same markup that
    will be sent to the recipient, without the outer mail wrapper template.
    Used both by :func:`make_html` (which wraps this in the full HTML email
    layout) and by the organiser outbox / mail-log previews, so the preview
    matches the delivered body byte-for-byte."""
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
    from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- slow markdown import
        render_markdown_abslinks,
    )

    return render_markdown_abslinks(mail.text)


def make_html(mail):
    event = getattr(mail, "event", None)
    sig = None
    if event:
        sig = event.mail_settings["signature"]
        if sig.strip().startswith("-- "):
            sig = sig.strip()[3:].strip()
    html_context = {
        "body": render_html_body(mail),
        "event": event,
        "color": (event.primary_color if event else "")
        or settings.DEFAULT_EVENT_PRIMARY_COLOR,
        "locale": mail.locale,
        "rtl": mail.locale in settings.LANGUAGES_BIDI,
        "subject": mail.subject,
        "signature": sig,
    }
    return get_template("mail/mailwrapper.html").render(html_context)


def make_text(mail):
    event = getattr(mail, "event", None)
    if not event or not event.mail_settings["signature"]:
        return mail.text
    sig = event.mail_settings["signature"]
    if not sig.strip().startswith("-- "):
        sig = f"-- \n{sig}"
    return f"{mail.text}\n{sig}"
