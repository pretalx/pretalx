# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import string
from decimal import Decimal

from django.dispatch import receiver
from django.template.defaultfilters import date as _date
from django.utils.safestring import SafeString, mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from urlman import UrlString

from pretalx.common.text.formatting import EmailAlternativeString
from pretalx.mail.placeholders import (
    LinkMailTextPlaceholder,
    TrustedMarkdownMailTextPlaceholder,
    TrustedPlainMailTextPlaceholder,
    UntrustedMarkdownMailTextPlaceholder,
    UntrustedPlainMailTextPlaceholder,
)
from pretalx.mail.signals import register_mail_placeholders
from pretalx.schedule.notifications import (
    get_current_notifications,
    get_full_notifications,
    get_notification_date_format,
    render_notifications,
)


def _validate_safe_extra_context(safe_extra_context):
    """Reject ``safe_extra_context`` values that aren't pre-sanitised:
    only ``SafeString``, ``EmailAlternativeString``, ``UrlString``,
    and numeric types pass."""
    if not safe_extra_context:
        return
    for key, value in safe_extra_context.items():
        if not isinstance(
            value, (SafeString, EmailAlternativeString, UrlString, int, float, Decimal)
        ):
            raise TypeError(
                f"safe_extra_context[{key!r}] must be a SafeString "
                f"(e.g. via django.utils.safestring.mark_safe), a "
                f"EmailAlternativeString, a urlman UrlString "
                f"(e.g. obj.urls.foo), or a numeric type, got "
                f"{type(value).__name__!r}. Wrap internally-built "
                "values in mark_safe, or register a placeholder for "
                "user-controlled values."
            )


def get_mail_context(*, safe_extra_context=None, **kwargs):
    """Resolve registered mail placeholders satisfied by ``kwargs``
    and return a ``{identifier: value}`` dict, merged with
    ``safe_extra_context`` (see :func:`_validate_safe_extra_context`)."""
    _validate_safe_extra_context(safe_extra_context)
    if safe_extra_context:
        safe_extra_context = {
            key: (
                mark_safe(value.full())  # noqa: S308  -- urlman-built internal URL
                if isinstance(value, UrlString)
                else value
            )
            for key, value in safe_extra_context.items()
        }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    event = kwargs.get("event")
    if "submission" in kwargs and "slot" not in kwargs:
        slot = kwargs["submission"].slot
        if slot and slot.start and slot.room:
            kwargs["slot"] = kwargs["submission"].slot
    context = {}
    for _recv, placeholders in register_mail_placeholders.send(sender=event):
        placeholder_list = (
            placeholders if isinstance(placeholders, (list, tuple)) else [placeholders]
        )
        for placeholder in placeholder_list:
            if all(required in kwargs for required in placeholder.required_context):
                context[placeholder.identifier] = placeholder.render(kwargs)
    if safe_extra_context:
        context.update(safe_extra_context)
    return context


def get_available_placeholders(event, kwargs):
    params = {}
    for _recv, placeholders in register_mail_placeholders.send(sender=event):
        placeholder_list = (
            placeholders if isinstance(placeholders, (list, tuple)) else [placeholders]
        )
        for placeholder in placeholder_list:
            if all(required in kwargs for required in placeholder.required_context):
                params[placeholder.identifier] = placeholder
    return params


def get_used_placeholders(text):
    if not text:
        return set()
    if isinstance(text, str):
        return {element[1] for element in string.Formatter().parse(text) if element[1]}
    if getattr(text, "data", None):
        return get_used_placeholders(text.data)
    if isinstance(text, dict):
        placeholders = set()
        for lang in text.values():
            placeholders |= get_used_placeholders(lang)
        return placeholders
    return set()


def get_invalid_placeholders(text, valid_placeholders):
    return get_used_placeholders(text) - set(valid_placeholders)


def get_all_reviews(submission):
    reviews = submission.reviews.all().filter(text__isnull=False)
    if not reviews:
        return ""
    texts = [review.text.strip() for review in reviews if review.text.strip()]
    if not texts:
        return ""
    return "\n\n--------------\n\n".join(texts)


def placeholder_aliases(identifiers, args, func, sample, explanation=None, *, cls):
    result = []
    is_visible = True
    for identifier in identifiers:
        result.append(
            cls(
                identifier,
                args,
                func,
                sample,
                explanation=explanation,
                is_visible=is_visible,
            )
        )
        is_visible = False
    return result


@receiver(register_mail_placeholders, dispatch_uid="pretalx_register_base_placeholders")
def base_placeholders(sender, **kwargs):
    # sender may be None for eventless mail rendering (e.g. User.reset_password
    # outside an event context). override(None) activates the default language.
    with override(sender.locale if sender is not None else None):
        date_format = get_notification_date_format()
        time = _date(now().replace(hour=9, minute=0), date_format)
        time2 = _date(now().replace(hour=11, minute=0), date_format)
    placeholders = [
        *placeholder_aliases(
            ["event_name", "event"],
            ["event"],
            lambda event: event.name,
            lambda event: event.name,
            _("The event’s full name"),
            cls=TrustedPlainMailTextPlaceholder,
        ),
        TrustedPlainMailTextPlaceholder(
            "event_slug",
            ["event"],
            lambda event: event.slug,
            lambda event: event.slug,
            _("The event’s short form, used in URLs"),
        ),
        LinkMailTextPlaceholder(
            "event_url",
            ["event"],
            lambda event: event.urls.base.full(),
            lambda event: f"https://pretalx.com/{event.slug}/",
            _("The event’s public base URL"),
        ),
        LinkMailTextPlaceholder(
            "event_schedule_url",
            ["event"],
            lambda event: event.urls.schedule.full(),
            lambda event: f"https://pretalx.com/{event.slug}/schedule/",
            _("The event’s public schedule URL"),
        ),
        LinkMailTextPlaceholder(
            "event_cfp_url",
            ["event"],
            lambda event: event.cfp.urls.base.full(),
            lambda event: f"https://pretalx.com/{event.slug}/cfp",
            _("The event’s public CfP URL"),
        ),
        LinkMailTextPlaceholder(
            "all_submissions_url",
            ["event", "user"],
            lambda event, user: event.urls.user_submissions.full(),
            "https://pretalx.example.com/democon/me/submissions/",
            _("URL to a user’s list of proposals"),
        ),
        LinkMailTextPlaceholder(
            "profile_page_url",
            ["event", "user"],
            lambda event, user: event.urls.user.full(),
            "https://pretalx.example.com/democon/me/",
            _("URL to a user’s private profile page."),
        ),
        TrustedPlainMailTextPlaceholder(
            "deadline",
            ["event"],
            lambda event: (
                _date(event.cfp.deadline.astimezone(event.tz), "SHORT_DATETIME_FORMAT")
                if event.cfp.deadline
                else ""
            ),
            lambda event: (
                _date(event.cfp.deadline.astimezone(event.tz), "SHORT_DATETIME_FORMAT")
                if event.cfp.deadline
                else ""
            ),
            _("The general CfP deadline"),
        ),
        *placeholder_aliases(
            ["proposal_code", "session_code", "code"],
            ["submission"],
            lambda submission: submission.code,
            "F8VVL",
            _("The proposal’s unique ID"),
            cls=TrustedPlainMailTextPlaceholder,
        ),
        LinkMailTextPlaceholder(
            "talk_url",
            ["slot"],
            lambda slot: slot.submission.urls.public.full(),
            "https://pretalx.example.com/democon/schedule/F8VVL/",
            _("The proposal’s public URL"),
        ),
        *placeholder_aliases(
            ["proposal_url", "edit_url", "submission_url"],
            ["submission"],
            lambda submission: submission.urls.user_base.full(),
            "https://pretalx.example.com/democon/me/submissions/F8VVL/",
            _("The speaker’s edit page for the proposal"),
            cls=LinkMailTextPlaceholder,
        ),
        LinkMailTextPlaceholder(
            "confirmation_link",
            ["submission"],
            lambda submission: submission.urls.confirm.full(),
            "https://pretalx.example.com/democon/me/submissions/F8VVL/confirm",
            _("Link to confirm a proposal after it has been accepted."),
        ),
        LinkMailTextPlaceholder(
            "withdraw_link",
            ["submission"],
            lambda submission: submission.urls.withdraw.full(),
            "https://pretalx.example.com/democon/me/submissions/F8VVL/withdraw",
            _("Link to withdraw the proposal"),
        ),
        *placeholder_aliases(
            ["proposal_title", "submission_title"],
            ["submission"],
            lambda submission: submission.title,
            _("This Is a Proposal Title"),
            _("The proposal’s title"),
            cls=UntrustedPlainMailTextPlaceholder,
        ),
        UntrustedPlainMailTextPlaceholder(
            "speakers",
            ["submission"],
            lambda submission: submission.display_speaker_names,
            "Jane Smith, Fred Jones",
            _("The name(s) of all speakers in this proposal."),
        ),
        *placeholder_aliases(
            ["session_type", "submission_type"],
            ["submission"],
            lambda submission: str(submission.submission_type.name),
            _("Session Type A"),
            _("The proposal’s session type"),
            cls=TrustedPlainMailTextPlaceholder,
        ),
        TrustedPlainMailTextPlaceholder(
            "track_name",
            ["submission"],
            lambda submission: str(submission.track.name) if submission.track else "",
            _("Track A"),
            _("The track the proposal belongs to"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_duration_minutes",
            ["submission"],
            lambda submission: submission.get_duration(),
            "30",
            _("Duration in minutes"),
        ),
        TrustedMarkdownMailTextPlaceholder(
            "all_reviews",
            ["submission"],
            get_all_reviews,
            _(
                "First review, agreeing with the proposal.\n\n--------- \n\nSecond review, containing heavy criticism!"
            ),
            _("All review texts for this proposal"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_start_date",
            ["slot"],
            lambda slot: _date(slot.local_start, "SHORT_DATE_FORMAT"),
            _date(now(), "SHORT_DATE_FORMAT"),
            _("The session’s start date"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_start_time",
            ["slot"],
            lambda slot: _date(slot.local_start, "TIME_FORMAT"),
            _date(now(), "TIME_FORMAT"),
            _("The session’s start time"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_end_date",
            ["slot"],
            lambda slot: _date(slot.local_end, "SHORT_DATE_FORMAT"),
            _date(now(), "SHORT_DATE_FORMAT"),
            _("The session’s end date"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_end_time",
            ["slot"],
            lambda slot: _date(slot.local_end, "TIME_FORMAT"),
            _date(now(), "TIME_FORMAT"),
            _("The session’s end time"),
        ),
        TrustedPlainMailTextPlaceholder(
            "session_room",
            ["slot"],
            lambda slot: str(slot.room),
            _("Room 101"),
            _("The session’s room"),
        ),
        UntrustedPlainMailTextPlaceholder(
            "name",
            ["user"],
            lambda user: user.name or "",
            _("Jane Doe"),
            _("The addressed user’s full name"),
        ),
        UntrustedPlainMailTextPlaceholder(
            "inviting_speaker",
            ["inviting_user"],
            lambda inviting_user: inviting_user.get_display_name(),
            _("Jane Doe"),
        ),
        UntrustedPlainMailTextPlaceholder(
            "email",
            ["user"],
            lambda user: user.email,
            "jane@example.org",
            _("The addressed user’s email address"),
        ),
        *placeholder_aliases(
            # TODO(rixx): https://github.com/pretalx/pretalx/issues/2336: remove alias in 2026, maybe
            ["speaker_schedule_new", "notifications"],
            ["user", "event"],
            lambda user, event: render_notifications(
                get_current_notifications(user, event), event
            ),
            _(
                "- Your session “Title” will take place at {time} in Room 101.\n"
                "- Your session “Other Title” has been moved to {time2} in Room 102."
            ).format(time=time, time2=time2),
            _(
                "A list of all changes to the user’s schedule in the current schedule version."
            ),
            cls=UntrustedMarkdownMailTextPlaceholder,
        ),
        UntrustedMarkdownMailTextPlaceholder(
            "speaker_schedule_full",
            ["user", "event"],
            lambda user, event: render_notifications(
                get_full_notifications(user, event), event
            ),
            _(
                "- Your session “Title” will take place at {time} in Room 101.\n"
                "- Your session “Other Title” will take place at {time2} in Room 102."
            ).format(time=time, time2=time2),
            _("Times and locations for this user\u2019s publicly visible sessions."),
        ),
    ]

    return placeholders  # noqa: RET504 -- explicit return aids debugger breakpoints
