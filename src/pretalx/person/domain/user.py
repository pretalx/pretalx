# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.db import models, transaction
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import get_language
from django_scopes import scopes_disabled
from urlman import UrlString

from pretalx.common.domain.queries.log import actions_by
from pretalx.common.exceptions import UserDeletionError
from pretalx.common.urls import build_absolute_uri
from pretalx.mail.domain.placeholders import untrusted_plain_value
from pretalx.mail.domain.send import send_system_mail
from pretalx.mail.template_phrases import (
    EMAIL_CHANGED_SUBJECT,
    EMAIL_CHANGED_TEXT,
    PASSWORD_CHANGED_SUBJECT,
    PASSWORD_CHANGED_TEXT,
    PASSWORD_RESET_SUBJECT,
    PASSWORD_RESET_TEXT,
)
from pretalx.person.models import User
from pretalx.person.signals import delete_user as delete_user_signal
from pretalx.submission.models import Answer, Submission


def create_user(*, email, name="", password=None, event=None, **kwargs):
    """Single entry point for creating ``User`` rows.

    When ``password`` is ``None``, a random password and a fresh
    ``pw_reset_token`` are generated so the new user can pick a real
    password via the standard recovery URL — this is the invitation
    flow used for speakers that are created rather than invited.

    Passing ``event`` materialises a ``SpeakerProfile`` for that event.

    Extra ``**kwargs`` are forwarded to the ``User`` constructor so
    callers can set ``locale``, ``timezone`` etc.; we default the latter
    two to the active request language/timezone rather than letting the
    model fall back to ``settings.LANGUAGE_CODE`` / ``UTC``.

    Runs the model invariants in ``User.clean`` before saving so every
    creation path enforces the email-uniqueness rule from
    :mod:`pretalx.person.validators`. Field-level
    validation (``clean_fields``) is intentionally not invoked here:
    the invitation flow legitimately creates users with an empty name,
    and ``code`` is populated by ``GenerateCode.save``.
    """
    name = (name or "").strip()
    kwargs.setdefault("locale", get_language())
    kwargs.setdefault("timezone", timezone.get_current_timezone_name())
    if password is None:
        password = get_random_string(32)
        kwargs["pw_reset_token"] = get_random_string(32)
        kwargs["pw_reset_time"] = timezone.now() + dt.timedelta(days=60)

    user = User(email=email, name=name, **kwargs)
    user.set_password(password)
    user.clean()
    user.save()
    if event:
        user.get_speaker(event=event)
    return user


@transaction.atomic
def deactivate_user(user):
    """Anonymise ``user`` in place: scramble email, blank personal data,
    drop pictures and team memberships, delete answers flagged as
    personal data."""
    user.email = f"deleted_user_{get_random_string(12)}@localhost"
    while User.objects.filter(email__iexact=user.email).exists():
        user.email = f"deleted_user_{get_random_string(12)}@localhost"
    user.name = "Deleted User"
    user.is_active = False
    user.is_superuser = False
    user.is_administrator = False
    user.locale = "en"
    user.timezone = "UTC"
    user.pw_reset_token = None
    user.pw_reset_time = None
    user.set_unusable_password()
    user.delete_files()
    user.profile_picture = None
    user.save()
    user.profiles.update(biography="")
    for answer in Answer.objects.filter(
        models.Q(speaker__user=user) | models.Q(submission__speakers__user=user),
        question__contains_personal_data=True,
    ).distinct():
        answer.delete()  # iterate to delete answer files too
    for team in user.teams.all():
        team.members.remove(user)
    delete_user_signal.send(None, user=user, db_delete=True)


@transaction.atomic
def shred_user(user):
    """Delete ``user`` outright. Refuses if the user still has
    submissions, answers or team memberships — call ``deactivate_user``
    in that case."""
    with scopes_disabled():
        if (
            Submission.all_objects.filter(speakers__user=user).exists()
            or user.teams.exists()
            or Answer.objects.filter(
                models.Q(speaker__user=user) | models.Q(submission__speakers__user=user)
            ).exists()
        ):
            raise UserDeletionError(
                f"Cannot delete user <{user.email}> because they have submissions, answers, or teams. Please deactivate this user instead."
            )
        user.logged_actions().delete()
        actions_by(user).update(person=None)
        user.delete_files()
        delete_user_signal.send(None, user=user, db_delete=True)
        user.delete()


def get_password_reset_url(user, *, event=None, orga=False):
    """URL the password-reset mail points at, namespaced by the orga
    flag and (optionally) the event slug."""
    if event:
        path = "orga:event.auth.recover" if orga else "cfp:event.recover"
        kwargs = {"token": user.pw_reset_token, "event": event.slug}
    else:
        path = "orga:auth.recover"
        kwargs = {"token": user.pw_reset_token}
    # Returning an :class:`urlman.UrlString` (a ``str`` subclass)
    # lets :func:`pretalx.mail.domain.context.get_mail_context` drop the
    # result into ``safe_extra_context`` without a separate
    # ``mark_safe`` wrap at every call site.
    return UrlString(build_absolute_uri(path, kwargs=kwargs))


@transaction.atomic
def reset_password(user, *, event=None, orga=False, log_actor=None, mail_text=None):
    """Mint a fresh ``pw_reset_token`` and queue the recovery mail.

    ``log_actor`` (orga who triggered the reset on behalf of the user)
    is logged on the activity entry; ``orga=True`` flips the recovery
    URL onto the orga namespace."""
    user.pw_reset_token = get_random_string(32)
    user.pw_reset_time = now()
    user.save(update_fields=["pw_reset_token", "pw_reset_time"])

    send_system_mail(
        subject=PASSWORD_RESET_SUBJECT,
        text=mail_text or PASSWORD_RESET_TEXT,
        to=user.email,
        event=event,
        locale=user.locale,
        safe_extra_context={
            "url": get_password_reset_url(user, event=event, orga=orga)
        },
        context_kwargs={"user": user},
    )
    user.log_action(
        action="pretalx.user.password.reset", person=log_actor, orga=bool(log_actor)
    )


@transaction.atomic
def change_password(user, new_password):
    """Set ``new_password``, clear any pending reset token, send the
    confirmation mail and log the change."""
    user.set_password(new_password)
    user.pw_reset_token = None
    user.pw_reset_time = None
    user.save(update_fields=["password", "pw_reset_token", "pw_reset_time"])

    send_system_mail(
        subject=PASSWORD_CHANGED_SUBJECT,
        text=PASSWORD_CHANGED_TEXT,
        to=user.email,
        locale=user.locale,
        context_kwargs={"user": user},
    )

    user.log_action("pretalx.user.password.update")


@transaction.atomic
def change_email(user, new_email):
    """Update the user's email, send a confirmation to the *previous*
    address and log the old/new pair."""
    old_email = user.email
    user.email = new_email
    user.clean()  # normalises and validates uniqueness
    user.save(update_fields=["email"])

    send_system_mail(
        subject=EMAIL_CHANGED_SUBJECT,
        text=EMAIL_CHANGED_TEXT,
        to=old_email,
        locale=user.locale,
        safe_extra_context={
            # Django's ``EmailField`` accepts RFC 5321 quoted local
            # parts (``"<script>"@example.com``), so we treat the
            # two address values as untrusted and route them
            # through the same escape pipeline as an
            # ``UntrustedPlain`` placeholder rather than marking
            # them safe.
            "old_email": untrusted_plain_value(old_email),
            "new_email": untrusted_plain_value(user.email),
        },
        context_kwargs={"user": user},
    )

    user.log_action(
        action="pretalx.user.email.update",
        person=user,
        orga=False,
        data={"old_email": old_email, "new_email": user.email},
    )
