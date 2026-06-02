# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q
from django.db.models.fields.files import FieldFile
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from pretalx.common.exceptions import SubmissionError
from pretalx.common.text.formatting import EmailAlternativeString
from pretalx.mail.domain.placeholders import escape_for_html_body, escape_for_plain_body
from pretalx.mail.domain.queue import save_draft
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_draft, send_transient
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.person.domain.user import create_user
from pretalx.person.models import SpeakerProfile, User
from pretalx.schedule.domain.slot import move_slot
from pretalx.schedule.tasks import task_update_unreleased_schedule_changes
from pretalx.submission.domain.access_code import redeem_access_code
from pretalx.submission.domain.invitation import send_invitation
from pretalx.submission.domain.review import recalculate_submission_scores
from pretalx.submission.enums import AttendeeSignupStates, SubmissionStates
from pretalx.submission.models import Answer, SpeakerRole, Submission
from pretalx.submission.signals import (
    before_submission_state_change,
    submission_state_change,
)
from pretalx.submission.tasks import task_send_initial_mails


def create_submission(
    *,
    submission,
    user,
    orga=False,
    speakers=(),
    tags=(),
    invite_addresses=(),
    send_initial_mails=False,
):
    """Persist a new Submission and apply create-time side effects.

    ``user`` is the creator (for log attribution); ``orga=True`` marks the
    creation as an organiser action in the log.
    ``invite_addresses`` is routed through ``apply_invite_addresses`` (parked
    for drafts, dispatched as invitations otherwise).

    Access-code redemption is skipped for DRAFT proposals (they may be
    abandoned, so the code must remain available); ``submit_draft`` consumes
    it once the draft becomes real. Likewise the create log is silently
    dropped by ``Submission.log_action`` while the state is DRAFT, and
    re-fired by ``submit_draft``.

    With ``send_initial_mails=True``, schedules the speaker acknowledgment
    (and optional organiser notification).

    Creates with a non-DRAFT, non-SUBMITTED initial state (the orga
    creating an already-accepted talk, say) fire ``before_submission_state_change``
    first so plugins can veto. Initial DRAFT/SUBMITTED transitions skip the
    signal, mirroring ``set_submission_state``.
    """
    is_speaker_state = submission.state in (
        SubmissionStates.SUBMITTED,
        SubmissionStates.DRAFT,
    )
    if not is_speaker_state:
        responses = before_submission_state_change.send_robust(
            submission.event,
            submission=submission,
            new_state=submission.state,
            user=user,
        )
        exceptions = [r[1] for r in responses if isinstance(r[1], SubmissionError)]
        if exceptions:
            raise exceptions[0]
    if submission._state.adding:
        submission.save()
    if submission.state != SubmissionStates.DRAFT:
        submission_state_change.send_robust(
            submission.event, submission=submission, old_state=None, user=user
        )
    update_talk_slots(submission)
    if tags:
        submission.tags.set(tags)
    # Initial speakers are folded into the ``.create`` log entry below;
    # passing no ``log_user`` to ``add_speaker`` skips its own
    # ``speakers.add`` log so the audit trail isn't duplicated.
    for speaker in speakers:
        add_speaker(submission, user=speaker)
    submission.log_action(".create", person=user, orga=orga)
    if submission.image:
        submission.process_image("image")
    if submission.access_code and submission.state != SubmissionStates.DRAFT:
        redeem_access_code(submission.access_code)
    apply_invite_addresses(submission, invite_addresses, sender=user)
    if send_initial_mails:
        queue_initial_mails(submission, person=user)
    return submission


def delete_submission(submission, *, person=None, orga=True):
    """Delete ``submission`` along with related rows that need per-instance
    cleanup.

    Answers and resources are deleted one by one so that the
    ``FileCleanupMixin`` override schedules attached files for removal;
    cascade and bulk-delete would bypass it. Reviewer answers are
    PROTECT'd by their FK to ``Review`` (which itself cascades from the
    submission), so they don't get cleaned up by the submission cascade
    and need an explicit pass. Slots are PROTECT'd too, so we drop them
    explicitly first.
    """
    submission.slots.all().delete()
    for answer in submission.answers.all():
        answer.delete()
    for answer in Answer.objects.filter(review__submission=submission):
        answer.delete()
    for resource in submission.resources.all():
        resource.delete()
    submission.delete(
        log_kwargs={
            "person": person,
            "orga": orga,
            "data": {
                "title": submission.title,
                "code": submission.code,
                "state": submission.state,
            },
        }
    )


def submit_draft(submission, *, user, invite_addresses=()):
    """Transition a DRAFT submission to SUBMITTED.

    Redeems the access code (deferred from draft creation), fires
    ``pretalx.submission.create`` — silenced while the proposal was a
    draft — now that the proposal exists for real, and routes
    ``invite_addresses`` through ``apply_invite_addresses`` (which by
    then dispatches them as real invitations). Wrapped in a transaction
    so the state change, code redemption, create log and invitation
    dispatch succeed or fail together.
    """
    with transaction.atomic():
        set_submission_state(submission, SubmissionStates.SUBMITTED, person=user)
        if submission.access_code:
            redeem_access_code(submission.access_code)
        submission.log_action(".create", person=user)
        apply_invite_addresses(submission, invite_addresses, sender=user)
    queue_initial_mails(submission, person=user)
    return submission


def queue_initial_mails(submission, *, person):
    """Queue the post-submit speaker acknowledgment with a 60-second
    delay for corrections and safety.
    """
    transaction.on_commit(
        lambda: task_send_initial_mails.apply_async(
            kwargs={"submission_id": submission.pk, "person_id": person.pk},
            countdown=60,
        )
    )


def apply_invite_addresses(submission, addresses, *, sender):
    """Route additional-speaker email addresses based on submission state.

    DRAFT proposals park ``addresses`` on ``draft_additional_speakers``
    so the speaker can resume the wizard later; non-DRAFT proposals
    dispatch each address as a ``SubmissionInvitation`` and clear any
    leftover parking. Idempotent on the parked list — only writes when
    the value changes.
    """
    addresses = list(addresses or [])
    if submission.state == SubmissionStates.DRAFT:
        if submission.draft_additional_speakers != addresses:
            submission.draft_additional_speakers = addresses
            submission.save(update_fields=["draft_additional_speakers"])
        return
    for address in addresses:
        send_invitation(submission, email=address, sender=sender)
    if submission.draft_additional_speakers:
        submission.draft_additional_speakers = []
        submission.save(update_fields=["draft_additional_speakers"])


def set_submission_state(
    submission, new_state, *, person=None, orga=False, from_pending=False
):
    """Transition a submission to ``new_state`` and persist.

    Handles the full lifecycle of a state change, including
    - ``before_submission_state_change`` veto signal (except for DRAFTs)
    - data handling, e.g. clearing ``is_featured`` in rejection states
    - database write
    - slot reconciliation
    - logging
    - state change email generation
    - ``submission_state_change`` signal

    When the old state and the new state are the same, none of this applies
    and only the pending state is cleared.
    """
    previous = submission.state
    if previous == new_state:
        set_pending_state(submission, None)
        return

    is_initial_submit = new_state == SubmissionStates.SUBMITTED and previous in (
        None,
        SubmissionStates.DRAFT,
    )
    if not is_initial_submit:
        responses = before_submission_state_change.send_robust(
            submission.event, submission=submission, new_state=new_state, user=person
        )
        exceptions = [r[1] for r in responses if isinstance(r[1], SubmissionError)]
        if exceptions:
            raise exceptions[0]

    submission.state = new_state
    submission.pending_state = None
    update_fields = ["state", "pending_state"]
    if new_state in (
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ):
        submission.is_featured = False
        update_fields.append("is_featured")

    submission.save(update_fields=update_fields)
    update_talk_slots(submission)

    if not is_initial_submit:
        submission.log_action(
            SubmissionStates.log_actions[new_state],
            person=person,
            orga=orga,
            data={"previous": previous, "from_pending": from_pending},
        )
        # Acceptance / rejection generates a decision mail. Un-confirming
        # (CONFIRMED → ACCEPTED) skips it; the speaker already got that mail.
        if new_state == SubmissionStates.REJECTED or (
            new_state == SubmissionStates.ACCEPTED
            and previous != SubmissionStates.CONFIRMED
        ):
            send_state_mail(submission)

    submission_state_change.send_robust(
        submission.event,
        submission=submission,
        old_state=previous if previous != SubmissionStates.DRAFT else None,
        user=person,
    )


def update_talk_slots(submission):
    """Reconcile ``TalkSlot`` rows on the wip schedule with the
    submission's state and ``slot_count``.

    If the submission is not (or pending-) accepted, all slots are
    removed; otherwise the count is brought up or down to ``slot_count``,
    deleting unscheduled slots first. Slot visibility tracks the
    CONFIRMED state.
    """
    wip = submission.event.wip_schedule
    talks = wip.talks.filter(submission=submission)
    scheduling_allowed = (
        submission.state in SubmissionStates.accepted_states
        or submission.pending_state in SubmissionStates.accepted_states
    )

    if not scheduling_allowed:
        talks.delete()
        return

    diff = talks.count() - submission.slot_count
    if diff > 0:
        # We delete unscheduled slots first; ``.delete()`` doesn't work on
        # sliced querysets, so collect IDs separately.
        to_delete = list(
            talks.order_by("start", "room", "is_visible")[:diff].values_list(
                "id", flat=True
            )
        )
        wip.talks.filter(pk__in=to_delete).delete()
    elif diff < 0:
        for __ in range(-diff):
            wip.talks.create(submission=submission)
    talks.update(is_visible=submission.state == SubmissionStates.CONFIRMED)


def update_duration(submission):
    """Push the submission's duration onto its currently scheduled wip
    slots so the schedule reflects the new length."""
    duration = submission.get_duration()
    for slot in submission.event.wip_schedule.talks.filter(
        submission=submission, start__isnull=False
    ):
        move_slot(slot, slot.start, duration=duration)


def pin_signup_required(submissions):
    """When a track or submission type switches attendee_signup_required
    from True to False, we manually set individual submissions to require
    signups if they already have attendees to prevent stranding them."""
    candidates = (
        submissions.filter(
            attendee_signup_required__isnull=True,
            attendee_signups__state=AttendeeSignupStates.CONFIRMED,
            submission_type__attendee_signup_required=False,
        )
        .filter(Q(track__isnull=True) | Q(track__attendee_signup_required=False))
        .distinct()
    )
    affected = list(candidates)
    if affected:
        Submission._base_manager.filter(pk__in=[s.pk for s in affected]).update(
            attendee_signup_required=True
        )
    return affected


def apply_field_changes(submission, changed_fields):
    """Run the side-effects keyed off the fields a caller just persisted.

    Callers pass an iterable of field names (typically ``form.changed_data``
    or a manually-built set in a serializer); this function dispatches to
    ``update_duration`` / ``update_talk_slots`` /
    ``recalculate_submission_scores`` for the fields that demand it. Other
    field names are ignored, so callers can pass their full ``changed_data``
    without filtering.
    """
    fields = set(changed_fields)
    if "duration" in fields:
        update_duration(submission)
    if "slot_count" in fields:
        update_talk_slots(submission)
    if "track" in fields:
        recalculate_submission_scores(submission)


def set_wip_slot(submission, *, room, start, end):
    """Apply ``room``/``start``/``end`` to the submission's wip slot, or
    drop scheduling entirely, then queue the unreleased-changes task.

    With ``room`` and ``start`` set (and the submission accepted), the
    earliest wip slot is updated in place. With ``start`` cleared, all wip
    slots are deleted and ``update_talk_slots`` recreates the bare ones.
    """
    if not (room and start and submission.state in SubmissionStates.accepted_states):
        submission.slots.filter(schedule=submission.event.wip_schedule).delete()
        update_talk_slots(submission)
    else:
        slot = (
            submission.slots.filter(schedule=submission.event.wip_schedule)
            .order_by("start")
            .first()
        )
        if slot is None:  # accepted submission with no wip slot — should not happen
            return
        move_slot(slot, start, room=room, end=end)
    task_update_unreleased_schedule_changes.apply_async(
        kwargs={"event": submission.event.slug}
    )


def send_state_mail(submission):
    """Queue the per-state notification mail for accept/reject."""
    if submission.state == SubmissionStates.ACCEPTED:
        template = mail_template_by_role(
            submission.event, MailTemplateRoles.SUBMISSION_ACCEPT
        )
    elif submission.state == SubmissionStates.REJECTED:
        template = mail_template_by_role(
            submission.event, MailTemplateRoles.SUBMISSION_REJECT
        )
    else:
        return

    for speaker in submission.sorted_speakers:
        mail = render_template_to_mail(
            template,
            locale=submission.get_email_locale(speaker.user.locale),
            context_kwargs={"submission": submission, "user": speaker.user},
        )
        save_draft(mail, to_users=[speaker.user], submissions=[submission])


def set_pending_state(submission, new_state):
    previous = submission.pending_state
    submission.pending_state = new_state
    submission.save(update_fields=["pending_state"])
    if (
        previous in SubmissionStates.accepted_states
        or new_state in SubmissionStates.accepted_states
    ):
        update_talk_slots(submission)


def apply_pending_state(submission, *, person=None):
    """Resolve a queued ``pending_state`` by transitioning to it.

    Pending applies are always orga-attributed: ``pending_state`` is set
    and applied from orga views exclusively.
    """
    if not submission.pending_state:
        return
    set_submission_state(
        submission,
        submission.pending_state,
        person=person,
        orga=True,
        from_pending=True,
    )


def send_initial_mails(submission, *, person):
    """Send the post-submit speaker confirmation and (optionally) the
    organiser notification.

    Both mails are dispatched immediately rather than left in the outbox
    for later sending. The speaker mail is also recorded in the outbox
    (via :func:`save_draft` + :func:`send_draft`); the organiser
    notification is fire-and-forget. The organiser-side mail is gated on
    ``mail_on_new_submission``."""
    template = mail_template_by_role(submission.event, MailTemplateRoles.NEW_SUBMISSION)
    locale = submission.get_email_locale(person.locale)
    with override(locale):
        if "{full_submission_content}" not in str(template.text):
            template.text = (
                str(template.text)
                + "\n\n\n***********\n\n"
                + str(_("Full proposal content:\n\n") + "{full_submission_content}")
            )
    mail = render_template_to_mail(
        template,
        context_kwargs={"user": person, "submission": submission},
        safe_extra_context={
            "full_submission_content": _content_for_mail_placeholder(
                submission, locale=locale
            )
        },
        locale=locale,
    )
    save_draft(mail, to_users=[person], submissions=[submission])
    send_draft(mail)
    if submission.event.mail_settings["mail_on_new_submission"]:
        internal_mail = render_template_to_mail(
            mail_template_by_role(
                submission.event, MailTemplateRoles.NEW_SUBMISSION_INTERNAL
            ),
            context_kwargs={"user": person, "submission": submission},
            safe_extra_context={"orga_url": submission.orga_urls.base},
            locale=submission.event.locale,
        )
        internal_mail.to = submission.event.email
        send_transient(internal_mail)


def invite_speaker(submission, *, email, name=None, locale=None, user=None):
    """Add a speaker by email and dispatch the appropriate invitation
    mail.

    Existing accounts get the EXISTING_SPEAKER_INVITE template; brand-new
    speakers are created via ``person.domain.user.create_user`` and get the
    NEW_SPEAKER_INVITE template along with their account-activation link.
    """
    safe_extra_context = {}
    try:
        speaker_user = User.objects.get(email__iexact=email)
        template_role = MailTemplateRoles.EXISTING_SPEAKER_INVITE
    except User.DoesNotExist:
        speaker_user = create_user(email=email, name=name, event=submission.event)
        speaker = speaker_user.get_speaker(submission.event)
        template_role = MailTemplateRoles.NEW_SPEAKER_INVITE
        safe_extra_context["invitation_link"] = speaker.urls.invitation

    speaker = add_speaker(submission, user=speaker_user, name=name, log_user=user)
    template = mail_template_by_role(submission.event, template_role)
    mail = render_template_to_mail(
        template,
        safe_extra_context=safe_extra_context,
        context_kwargs={
            "user": speaker_user,
            "submission": submission,
            "event": submission.event,
        },
        locale=locale or submission.event.locale,
    )
    save_draft(mail, to_users=[speaker_user], submissions=[submission])
    return speaker


def add_speaker(submission, *, user=None, speaker=None, name=None, log_user=None):
    """Attach a speaker to a submission and place them at the end of
    the speaker list. ``user`` and ``speaker`` are mutually exclusive
    inputs: pass an existing :class:`SpeakerProfile` or a :class:`User`
    plus optional name to materialise one. Logs the addition only when
    ``log_user`` is supplied.
    """
    if not speaker:
        speaker, _created = SpeakerProfile.objects.get_or_create(
            user=user, event=submission.event, defaults={"name": name or user.name}
        )
    submission.speakers.add(speaker)
    max_position = (
        submission.speaker_roles.exclude(speaker=speaker)
        .aggregate(max_pos=Max("position"))
        .get("max_pos")
    )
    submission.speaker_roles.filter(speaker=speaker).update(
        position=(max_position or 0) + 1
    )
    if log_user:
        submission.log_action(
            "pretalx.submission.speakers.add",
            person=log_user,
            orga=True,
            data={
                "code": speaker.code,
                "name": speaker.get_display_name(),
                "email": speaker.user.email,
            },
        )
    return speaker


def reorder_speakers(submission, *, role_ids, person=None, orga=True):
    roles = list(submission.speaker_roles.select_related("speaker", "speaker__user"))
    old_order = "\n".join(f"- {role.speaker.get_display_name()}" for role in roles)
    role_map = {str(role.pk): role for role in roles}

    for index, pk in enumerate(role_ids):
        if pk not in role_map:
            raise ValueError(f"Unknown speaker role: {pk!r}")
        role_map[pk].position = index
    SpeakerRole.objects.bulk_update(role_map.values(), ["position"])

    new_order = "\n".join(
        f"- {role_map[pk].speaker.get_display_name()}"
        for pk in role_ids
        if pk in role_map
    )
    if old_order == new_order:
        return
    submission.log_action(
        "pretalx.submission.speakers.reorder",
        person=person,
        orga=orga,
        old_data={"speakers": old_order},
        new_data={"speakers": new_order},
    )


def remove_speaker(submission, speaker, *, orga=True, user=None):
    """Detach ``speaker`` from the submission and log the removal.
    Idempotent: removing a speaker who is not attached is a no-op."""
    if not submission.speakers.filter(code=speaker.code).exists():
        return
    submission.speakers.remove(speaker)
    submission.log_action(
        "pretalx.submission.speakers.remove",
        person=user or speaker.user,
        orga=orga,
        data={
            "code": speaker.code,
            "email": speaker.user.email,
            "name": speaker.get_display_name(),
        },
    )


def _collect_content_fields(submission):
    """Yield ``(field_name, field_value)`` strings for every non-empty
    model field and custom-question answer on a submission. Used to build
    the ``{full_submission_content}`` mail placeholder sent to speakers and
    organisers."""
    base_url = submission.event.custom_domain or settings.SITE_URL
    cfp_flow = submission.event.cfp_flow

    def display(value):
        if isinstance(value, bool):
            return str(_("Yes") if value else _("No"))
        if isinstance(value, FieldFile):
            return base_url + value.url
        return str(value)

    for field in (
        "title",
        "abstract",
        "description",
        "notes",
        "duration",
        "content_locale",
        "do_not_record",
        "image",
    ):
        value = getattr(submission, field, None)
        if not value:
            continue
        meta = submission._meta.get_field(field)
        label = cfp_flow.get_field_config(cfp_flow.STEP_INFO, field).get("label")
        name = str(label) if label else str(meta.verbose_name or meta.name)
        yield name, display(value)
    for answer in submission.answers.select_related("question").order_by(
        "question__position"
    ):
        if answer.question.variant == "boolean":
            value = answer.boolean_answer
        elif answer.answer_file:
            value = answer.answer_file
        else:
            value = answer.answer or "-"
        yield str(answer.question.question), display(value)


def _content_for_mail_placeholder(submission, *, locale):
    """Build the :class:`EmailAlternativeString` for the
    ``{full_submission_content}`` placeholder: organiser-authored
    field names in bold, values escaped as untrusted-plain."""
    plain_parts = []
    html_parts = []
    with override(locale):
        for name, value in _collect_content_fields(submission):
            plain_parts.append(f"**{name}**: {escape_for_plain_body(value)}")
            html_parts.append(f"**{name}**: {escape_for_html_body(value)}")
    return EmailAlternativeString(
        plain="\n\n".join(plain_parts), html="\n\n".join(html_parts)
    )


def available_tracks_for_submitter(event, *, access_code=None, instance=None):
    """Tracks a submitter may pick when creating or editing a proposal.

    With an access code that has dedicated tracks, returns those.
    Otherwise returns tracks not requiring an access code, plus the
    instance's current track if any (so an existing selection is
    preserved even if its track later gains an access-code requirement).
    """
    if access_code and access_code.tracks.exists():
        return access_code.tracks.all()
    track_filter = Q(requires_access_code=False)
    if instance and instance.track and instance.track.requires_access_code:
        track_filter |= Q(pk=instance.track_id)
    return event.tracks.filter(track_filter)


def available_submission_types_for_submitter(event, *, access_code=None, instance=None):
    """Submission types a submitter may pick when creating or editing.

    Locks to the instance's current type once the proposal has moved past
    SUBMITTED or the CfP is closed; otherwise filters by access code, by
    per-type and global deadlines, and always includes the instance's
    current type so an existing selection survives a deadline.
    """
    submission_types = event.submission_types
    if (
        instance
        and not instance._state.adding
        and (instance.state != SubmissionStates.SUBMITTED or not event.cfp.is_open)
    ):
        return submission_types.filter(pk=instance.submission_type_id)

    if access_code and access_code.submission_types.exists():
        pks = set(access_code.submission_types.values_list("pk", flat=True))
    elif access_code:
        pks = set(
            submission_types.filter(requires_access_code=False).values_list(
                "pk", flat=True
            )
        )
    else:
        queryset = submission_types.filter(requires_access_code=False)
        _now = now()
        if not event.cfp.deadline or event.cfp.deadline >= _now:
            queryset = queryset.exclude(deadline__lt=_now)
        else:
            queryset = queryset.filter(deadline__gte=_now)
        pks = set(queryset.values_list("pk", flat=True))

    if instance and not instance._state.adding:
        pks |= {instance.submission_type_id}
    return submission_types.filter(pk__in=pks)
