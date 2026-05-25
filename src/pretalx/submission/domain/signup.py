# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from pretalx.common.exceptions import SubmissionError
from pretalx.person.models import AttendeeProfile
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup, Submission


def email_domain_allowed(event, email):
    domains = (event.attendee_signup_settings or {}).get("signup_domains") or []
    if not domains:
        return True
    if not email or "@" not in email:
        return False
    user_domain = email.lower().rsplit("@", 1)[-1]
    return user_domain in [d.lower() for d in domains]


def can_user_signup(submission, user):
    if not user or not user.is_authenticated:
        return False
    event = submission.event
    if not event.get_feature_flag("attendee_signup"):
        return False
    if not submission.requires_signup:
        return False
    return email_domain_allowed(event, user.email)


def get_signup_for_user(submission, user):
    if not user or not user.is_authenticated:
        return None
    return submission.attendee_signups.filter(attendee__user=user).first()


def get_confirmed_signup_for_user(submission, user):
    signup = get_signup_for_user(submission, user)
    if signup and signup.state == AttendeeSignupStates.CONFIRMED:
        return signup
    return None


def create_signup(submission, *, user):
    event = submission.event
    if not event.get_feature_flag("attendee_signup"):
        raise SubmissionError(_("Attendee signup is not enabled for this event."))
    if not submission.requires_signup:
        raise SubmissionError(_("This session does not require attendee signup."))
    if not email_domain_allowed(event, user.email):
        # Not revealing email domain config
        raise SubmissionError(_("You cannot sign up for this session."))

    with transaction.atomic():
        locked = Submission.objects.select_for_update().get(pk=submission.pk)
        profile, _created = AttendeeProfile.objects.get_or_create(
            event=event, user=user
        )
        signup = locked.attendee_signups.filter(attendee=profile).first()
        if signup and signup.state == AttendeeSignupStates.CONFIRMED:
            return signup
        capacity = locked.effective_signup_capacity
        if capacity is not None:
            current = locked.attendee_signups.filter(
                state=AttendeeSignupStates.CONFIRMED
            ).count()
            if current >= capacity:
                raise SubmissionError(_("This session is currently full."))
        if signup is None:
            signup = AttendeeSignup.objects.create(
                submission=locked,
                attendee=profile,
                state=AttendeeSignupStates.CONFIRMED,
            )
        else:
            signup.state = AttendeeSignupStates.CONFIRMED
            signup.save(update_fields=["state"])
        signup.log_action(".signup", person=user)
    return signup


def cancel_signup(submission, *, user):
    with transaction.atomic():
        locked = Submission.objects.select_for_update().get(pk=submission.pk)
        signup = get_confirmed_signup_for_user(locked, user)
        if not signup:
            return None
        signup.state = AttendeeSignupStates.CANCELED
        signup.save(update_fields=["state"])
        signup.log_action(".cancel", person=user)
    return signup
