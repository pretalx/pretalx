# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

DEFAULT_MAX_SPEAKERS = 50


def validate_speakers_within_limit(event, *, current, pending, additional):
    """Raise if adding more speakers would exceed the per-proposal limit.

    ``current`` is the number of speakers already on the proposal (count
    1 for an unsaved proposal where the submitter is the first speaker),
    ``pending`` the number of unaccepted invitations, and ``additional``
    the number of new speakers about to be added or invited.

    Deliberately not wired into ``Submission.clean()``: the limit gates
    the *act of adding* a speaker, not the proposal's persistent state.
    Once speakers are on a proposal, blocking unrelated edits because
    ``current > max_speakers`` (e.g. an organiser lowered the limit, or
    a reviewer is updating a different field) would be hostile, and a
    validation error cannot force a speaker removal.
    """
    max_speakers = event.cfp.max_speakers
    if max_speakers is None:
        max_speakers = DEFAULT_MAX_SPEAKERS
    if current + pending + additional > max_speakers:
        raise ValidationError(
            _(
                "This would exceed the maximum of {max} speakers per proposal. "
                "Currently: {current} speaker(s) and {pending} pending invitation(s)."
            ).format(max=max_speakers, current=current, pending=pending)
        )


def validate_invitation_target(submission, email):
    if submission.speakers.filter(user__email__iexact=email).exists():
        raise ValidationError(_("This person is already a speaker on this proposal."))
    if submission.invitations.filter(email__iexact=email).exists():
        raise ValidationError(
            _("This person has already been invited to this proposal.")
        )
    validate_speakers_within_limit(
        submission.event,
        current=submission.speakers.count(),
        pending=submission.invitations.count(),
        additional=1,
    )
