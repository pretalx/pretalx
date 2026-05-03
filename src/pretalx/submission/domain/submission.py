# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from pretalx.submission.domain.invitation import send_invitation
from pretalx.submission.enums import SubmissionStates


def create_submission(*, submission, user, speakers=(), tags=(), invite_addresses=()):
    """Persist a new Submission and apply create-time side effects.

    ``user`` is the creator (for log attribution).
    ``invite_addresses`` is routed through ``apply_invite_addresses`` (parked
    for drafts, dispatched as invitations otherwise).

    Access-code redemption is skipped for DRAFT proposals (they may be
    abandoned, so the code must remain available); ``submit_draft`` consumes
    it once the draft becomes real. Likewise the create log is silently
    dropped by ``Submission.log_action`` while the state is DRAFT, and
    re-fired by ``submit_draft``.
    """
    if submission.pk is None:
        submission.save()
    if tags:
        submission.tags.set(tags)
    for speaker in speakers:
        submission.add_speaker(user=speaker)
    submission.log_action("pretalx.submission.create", person=user)
    if submission.image:
        submission.process_image("image")
    if submission.access_code and submission.state != SubmissionStates.DRAFT:
        submission.access_code.redeem()
    apply_invite_addresses(submission, invite_addresses, sender=user)
    return submission


def make_submitted(submission, *, person=None, orga=False, from_pending=False):
    """Transition a submission to the SUBMITTED state.

    Logs ``pretalx.submission.make_submitted`` only when the previous
    state was something other than DRAFT — the DRAFT → SUBMITTED
    transition is the proposal becoming real, and ``submit_draft`` fires
    ``pretalx.submission.create`` for that case instead.
    """
    previous = submission.state
    submission.set_state(SubmissionStates.SUBMITTED, person=person)
    if previous != SubmissionStates.DRAFT:
        submission.log_action(
            "pretalx.submission.make_submitted",
            person=person,
            orga=orga,
            data={"previous": previous, "from_pending": from_pending},
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
        make_submitted(submission, person=user)
        if submission.access_code:
            submission.access_code.redeem()
        submission.log_action("pretalx.submission.create", person=user)
        apply_invite_addresses(submission, invite_addresses, sender=user)
    return submission


def apply_invite_addresses(submission, addresses, *, sender):
    """Route additional-speaker email addresses based on submission state.

    DRAFT proposals park ``addresses`` on ``draft_additional_speakers``
    so the speaker can resume the wizard later; non-DRAFT proposals
    dispatch each address as a ``SubmissionInvitation`` and clear any
    leftover parking. Idempotent on the parked list — only writes when
    the value changes.
    """
    addresses = list(addresses)
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
        and instance.pk
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

    if instance and instance.pk:
        pks |= {instance.submission_type_id}
    return submission_types.filter(pk__in=pks)
