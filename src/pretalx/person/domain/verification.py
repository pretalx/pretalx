# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import math

from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.timezone import now
from urlman import UrlString

from pretalx.common.urls import build_absolute_uri
from pretalx.mail.domain.placeholders import untrusted_plain_value
from pretalx.mail.domain.send import send_system_mail
from pretalx.mail.template_phrases import (
    EMAIL_CHANGE_REQUESTED_SUBJECT,
    EMAIL_CHANGE_REQUESTED_TEXT,
    EMAIL_CHANGED_SUBJECT,
    EMAIL_CHANGED_TEXT,
    EMAIL_VERIFICATION_SUBJECT,
    EMAIL_VERIFICATION_TEXT,
)
from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from pretalx.person.validators import validate_email_unique

VERIFICATION_SALT = "email-verification"
VERIFICATION_LINK_MAX_AGE = dt.timedelta(hours=24)
PENDING_EMAIL_MAX_AGE = dt.timedelta(hours=24)
SEND_COOLDOWN = dt.timedelta(minutes=5)

KIND_VERIFY = "verify"
KIND_CHANGE = "change"


class VerificationError(Exception):
    pass


class InvalidVerificationTokenError(VerificationError):
    pass


class ExpiredVerificationTokenError(VerificationError):
    pass


class PendingEmailExpiredError(VerificationError):
    pass


class PendingEmailTakenError(VerificationError):
    pass


def _token_check(user, kind):
    value = f"{kind}:{user.email}:{user.pending_email or ''}"
    return salted_hmac(VERIFICATION_SALT, value, algorithm="sha256").hexdigest()[:16]


def make_verification_token(user, kind):
    if kind == KIND_CHANGE and not user.pending_email:
        raise ValueError("Cannot make a change token without a pending email address")
    return signing.dumps(
        {"user": user.code, "kind": kind, "check": _token_check(user, kind)},
        salt=VERIFICATION_SALT,
    )


def parse_verification_token(token):
    try:
        payload = signing.loads(
            token, salt=VERIFICATION_SALT, max_age=VERIFICATION_LINK_MAX_AGE
        )
    except signing.SignatureExpired as error:
        raise ExpiredVerificationTokenError from error
    except signing.BadSignature as error:
        raise InvalidVerificationTokenError from error
    user = User.objects.filter(code=payload.get("user")).first()
    kind = payload.get("kind")
    if not user or kind not in (KIND_VERIFY, KIND_CHANGE):
        raise InvalidVerificationTokenError
    if not constant_time_compare(payload.get("check", ""), _token_check(user, kind)):
        raise InvalidVerificationTokenError
    return user, kind


def get_verification_url(token, *, event=None, orga=False):
    if event:
        path = "orga:event.auth.verify" if orga else "cfp:event.verify"
        kwargs = {"token": token, "event": event.slug}
    else:
        path = "orga:auth.verify"
        kwargs = {"token": token}
    return UrlString(build_absolute_uri(path, kwargs=kwargs))


def _cooldown_key(user):
    return f"pretalx_email_verification_cooldown_{user.pk}"


def send_cooldown_remaining(user):
    sent = cache.get(_cooldown_key(user))
    if not sent:
        return 0
    remaining = SEND_COOLDOWN.total_seconds() - (now().timestamp() - sent)
    return max(0, math.ceil(remaining))


def send_verification_mail(user, kind, *, event=None, orga=False):
    to = user.pending_email if kind == KIND_CHANGE else user.email
    if not to:
        raise ValueError("Cannot send a change link without a pending email address")
    token = make_verification_token(user, kind)
    send_system_mail(
        subject=EMAIL_VERIFICATION_SUBJECT,
        text=EMAIL_VERIFICATION_TEXT,
        to=to,
        event=event,
        locale=user.locale,
        safe_extra_context={"url": get_verification_url(token, event=event, orga=orga)},
        context_kwargs={"user": user},
    )
    cache.set(
        _cooldown_key(user), now().timestamp(), timeout=SEND_COOLDOWN.total_seconds()
    )
    user.log_action(
        "pretalx.user.email.verification.send", data={"email": to, "kind": kind}
    )


def pending_email_expired(user):
    return bool(user.pending_email_sent) and (
        now() - user.pending_email_sent > PENDING_EMAIL_MAX_AGE
    )


def _clear_pending_email(user):
    user.pending_email = None
    user.pending_email_sent = None
    user.save(update_fields=["pending_email", "pending_email_sent"])


def confirm_verification(user, token):
    token_user, kind = parse_verification_token(token)
    if token_user.pk != user.pk:
        raise InvalidVerificationTokenError

    if kind == KIND_CHANGE:
        if pending_email_expired(user):
            expired = user.pending_email
            _clear_pending_email(user)
            user.log_action(
                "pretalx.user.email.change.expire", data={"pending_email": expired}
            )
            raise PendingEmailExpiredError
        with transaction.atomic():
            address = user.pending_email
            try:
                validate_email_unique(address, exclude_user=user)
            except ValidationError as error:
                raise PendingEmailTakenError from error
            old_email = user.email
            user.email = address
            user.pending_email = None
            user.pending_email_sent = None
            user.email_verification_state = EmailVerificationState.VERIFIED
            user.save(
                update_fields=[
                    "email",
                    "pending_email",
                    "pending_email_sent",
                    "email_verification_state",
                ]
            )
            send_system_mail(
                subject=EMAIL_CHANGED_SUBJECT,
                text=EMAIL_CHANGED_TEXT,
                to=old_email,
                locale=user.locale,
                safe_extra_context={
                    "old_email": untrusted_plain_value(old_email),
                    "new_email": untrusted_plain_value(user.email),
                },
                context_kwargs={"user": user},
            )
            user.log_action(
                "pretalx.user.email.change.confirm",
                data={"old_email": old_email, "new_email": user.email},
            )
    else:
        with transaction.atomic():
            user.email_verification_state = EmailVerificationState.VERIFIED
            user.save(update_fields=["email_verification_state"])
            user.log_action(
                "pretalx.user.email.verification.confirm", data={"email": user.email}
            )


@transaction.atomic
def request_email_change(user, address, *, event=None, orga=False):
    address = address.lower().strip()
    validate_email_unique(address, exclude_user=user)
    user.pending_email = address
    user.pending_email_sent = now()
    user.save(update_fields=["pending_email", "pending_email_sent"])
    send_verification_mail(user, KIND_CHANGE, event=event, orga=orga)
    send_system_mail(
        subject=EMAIL_CHANGE_REQUESTED_SUBJECT,
        text=EMAIL_CHANGE_REQUESTED_TEXT,
        to=user.email,
        event=event,
        locale=user.locale,
        safe_extra_context={"pending_email": untrusted_plain_value(address)},
        context_kwargs={"user": user},
    )
    user.log_action(
        "pretalx.user.email.change.request", data={"pending_email": address}
    )


def cancel_email_change(user):
    if not user.pending_email:
        return
    pending = user.pending_email
    _clear_pending_email(user)
    user.log_action("pretalx.user.email.change.cancel", data={"pending_email": pending})


@transaction.atomic
def correct_unverified_email(user, address, *, event=None, orga=False):
    if user.email_verification_state != EmailVerificationState.UNVERIFIED:
        raise VerificationError(
            "Only unverified accounts may correct their address directly"
        )
    old_email = user.email
    user.email = address
    user.clean()  # normalises and validates uniqueness
    user.save(update_fields=["email"])
    send_verification_mail(user, KIND_VERIFY, event=event, orga=orga)
    user.log_action(
        "pretalx.user.email.verification.correct",
        data={"old_email": old_email, "new_email": user.email},
    )


def promote_on_invitation_match(user, invited_email):
    if not invited_email:
        return False
    if invited_email.strip().lower() != user.email.lower():
        return False
    if user.email_verification_state != EmailVerificationState.VERIFIED:
        user.email_verification_state = EmailVerificationState.VERIFIED
        user.save(update_fields=["email_verification_state"])
        user.log_action(
            "pretalx.user.email.verification.promote", data={"email": user.email}
        )
    return True


def finalize_registration(user, request, invited_email=None):
    if promote_on_invitation_match(user, invited_email):
        return
    send_verification_mail(
        user,
        KIND_VERIFY,
        event=getattr(request, "event", None),
        orga=request.path.startswith("/orga"),
    )
