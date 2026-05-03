# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_speakers_within_limit(event, *, current, pending, additional):
    """Raise if adding more speakers would exceed cfp.max_speakers.

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
        return
    if current + pending + additional > max_speakers:
        raise ValidationError(
            _(
                "This would exceed the maximum of {max} speakers per proposal. "
                "Currently: {current} speaker(s) and {pending} pending invitation(s)."
            ).format(max=max_speakers, current=current, pending=pending)
        )
