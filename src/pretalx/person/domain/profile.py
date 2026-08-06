# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.queue import save_draft
from pretalx.mail.domain.recipient import Recipient
from pretalx.mail.domain.render import render_to_mail
from pretalx.mail.domain.send import send_draft
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import SpeakerRole

MERGE_PROFILE_FIELDS = ("name", "biography", "email", "locale")


def create_speaker_profile(event, *, name=None, email=None, locale=None, log_user=None):
    """Create a managed, organiser-created speaker profile.

    Invitation sending must be handled separately."""
    if not email and not name:
        raise ValueError("create_speaker_profile() requires an email or a name")
    profile = SpeakerProfile(
        event=event,
        name=name or None,
        email=email or None,
        locale=locale or None,
        origin=SpeakerProfileOrigin.ORGA,
    )
    profile.save()
    profile.log_action(
        "pretalx.speaker.create",
        person=log_user,
        orga=True,
        data={"email": profile.effective_email, "name": profile.get_display_name()},
    )
    return profile


def send_speaker_invite(profile, *, subject, text, submission=None, log_user=None):
    """Set (or rotate) the invite token and dispatch the mail."""
    if profile.user_id:
        raise SendMailException(
            _("This speaker already has an account and needs no invitation.")
        )
    if not profile.effective_email:
        raise SendMailException(
            _(
                "This speaker has no contact email address, so no invitation can be sent."
            )
        )
    if not subject or not text:
        raise ValueError("send_speaker_invite() requires subject and text")

    locale = profile.effective_locale
    if submission:
        locale = submission.get_email_locale(locale)
    context_kwargs = {"user": Recipient(profile)}
    if submission:
        context_kwargs["submission"] = submission

    old_token, old_sent = profile.invitation_token, profile.invitation_sent
    profile.invitation_token = get_random_string(32)
    profile.invitation_sent = now()
    try:
        mail = render_to_mail(
            subject_template=subject,
            text_template=text,
            event=profile.event,
            locale=locale,
            context_kwargs=context_kwargs,
            safe_extra_context={"invitation_link": profile.urls.invitation},
        )
    except (SendMailException, ValueError) as error:
        profile.invitation_token, profile.invitation_sent = old_token, old_sent
        if isinstance(error, ValueError):
            raise SendMailException(f"Invalid invitation text: {error!s}") from error
        raise
    profile.save(update_fields=["invitation_token", "invitation_sent"])
    save_draft(
        mail, to_speakers=[profile], submissions=[submission] if submission else None
    )
    send_draft(mail, requestor=log_user)
    profile.log_action(
        "pretalx.speaker.invite.send",
        person=log_user,
        orga=True,
        data={"email": profile.effective_email},
    )
    return mail


def retract_speaker_invite(profile, *, log_user=None):
    if not profile.invitation_token:
        return
    email = profile.effective_email
    profile.invitation_token = None
    profile.save(update_fields=["invitation_token"])
    profile.log_action(
        "pretalx.speaker.invite.retract",
        person=log_user,
        orga=True,
        data={"email": email},
    )


def profile_deletable_after_removal(profile, submission, *, user):
    """Whether removing the given profile from a submission leaves a profile
    that the user user may delete — i.e. a managed profile whose only session
    this was."""
    if not profile.is_managed:
        return False
    profile.submission_count = profile.submissions.exclude(pk=submission.pk).count()
    return profile.submission_count == 0 and user.has_perm(
        "person.delete_speakerprofile", profile
    )


@transaction.atomic
def shred_speaker_profile(profile, *, user=None):
    """Delete a submission-less speaker profile."""
    if not profile.is_managed:
        raise ValueError("Only managed speaker profiles can be deleted this way.")
    if profile.submissions.exists():
        raise ValueError("Speaker profiles with submissions cannot be deleted.")

    data = {
        "code": profile.code,
        "name": profile.get_display_name(),
        "email": profile.effective_email,
    }
    event = profile.event
    profile.mails.all().delete()
    for answer in profile.answers.all():
        answer.delete()  # iterate to delete answer files too
    profile.feedback.all().delete()
    profile.logged_actions().delete()
    if picture := profile.profile_picture:
        # Bump the timestamp so the regular file cleanup picks it up.
        picture.save(update_fields=["updated"])
    profile.delete()
    event.log_action("pretalx.speaker.delete", person=user, orga=True, data=data)


def adopt_profile_picture(profile, user):
    picture = profile.profile_picture
    if not picture:
        return
    if picture.user_id is None:
        picture.user = user
        picture.save(update_fields=["user"])
    if not user.profile_picture_id:
        user.profile_picture = picture
        user.save(update_fields=["profile_picture"])


@transaction.atomic
def claim_speaker_profile(profile, user):
    profile.user = user
    profile.invitation_token = None
    profile.save(update_fields=["user", "invitation_token"])
    adopt_profile_picture(profile, user)
    profile.log_action("pretalx.speaker.claim", person=user)
    return profile


@transaction.atomic
def merge_speaker_profiles(merged, survivor, *, choices, user=None):
    log_data = {"merged_code": merged.code, "choices": dict(choices)}

    for field in MERGE_PROFILE_FIELDS:
        if choices.get(field) == "merged":
            setattr(survivor, field, getattr(merged, field))

    if merged.internal_notes:
        log_data["internal_notes_merged"] = True
        if survivor.internal_notes:
            survivor.internal_notes = (
                f"{survivor.internal_notes}\n\n{merged.internal_notes}"
            )
        else:
            survivor.internal_notes = merged.internal_notes
    if merged.has_arrived and not survivor.has_arrived:
        survivor.has_arrived = True
        log_data["has_arrived_merged"] = True

    discarded_picture = merged.profile_picture
    if choices.get("picture") == "merged" and merged.profile_picture:
        discarded_picture = survivor.profile_picture
        survivor.profile_picture = merged.profile_picture
        merged.profile_picture = None
        merged.save(update_fields=["profile_picture"])
        adopt_profile_picture(survivor, survivor.user)
    if discarded_picture:
        # Bump the timestamp so the regular file cleanup picks it up.
        discarded_picture.save(update_fields=["updated"])

    if choices.get("availability") == "merged":
        survivor.availabilities.all().delete()
        merged.availabilities.update(person=survivor)
    else:
        merged.availabilities.all().delete()

    survivor_answers = {answer.question_id: answer for answer in survivor.answers.all()}
    for answer in merged.answers.select_related("question"):
        choice = choices.get(f"question_{answer.question_id}")
        existing = survivor_answers.get(answer.question_id)
        if choice == "merged" or (choice is None and existing is None):
            if existing:
                existing.delete()
            answer.speaker = survivor
            answer.save(update_fields=["speaker"])
        else:
            answer.delete()

    survivor_submissions = set(
        SpeakerRole.objects.filter(speaker=survivor).values_list(
            "submission_id", flat=True
        )
    )
    for role in SpeakerRole.objects.filter(speaker=merged):
        if role.submission_id in survivor_submissions:
            role.delete()
        else:
            role.speaker = survivor
            role.save(update_fields=["speaker"])

    merged.feedback.update(speaker=survivor)

    for mail in merged.mails.all():
        mail.to_speakers.add(survivor)
        mail.to_speakers.remove(merged)

    merged.delete()
    survivor.save()
    survivor.log_action("pretalx.speaker.merge", person=user, data=log_data)
    return survivor


def apply_speaker_profile_changes(profile, changed_fields):
    """Run the side-effects keyed off the fields a caller just persisted on
    a speaker profile.
    """
    user = profile.user
    if not user:
        return
    if "name" in set(changed_fields) and profile.name and not user.name:
        user.name = profile.name
        user.save(update_fields=["name"])
