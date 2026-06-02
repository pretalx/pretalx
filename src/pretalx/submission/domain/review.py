# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import itertools

from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _


def update_review_score(review):
    """Recompute and persist ``review.score`` from its m2m ``scores``.

    Filters by the submission's currently applicable score categories
    (which depend on the submission's track) and writes the result back.
    """
    scores = list(
        review.scores.select_related("category").filter(
            category__in=review.submission.score_categories
        )
    )
    review.score = sum(s.value * s.category.weight for s in scores) if scores else None
    review.save()


def recalculate_event_scores(event):
    for review in event.reviews.all():
        update_review_score(review)


def recalculate_submission_scores(submission):
    for review in submission.reviews.all():
        update_review_score(review)


def validate_review_phases(event):
    review_phases = list(event.review_phases.all())
    for phase, next_phase in itertools.pairwise(review_phases):
        if not phase.end:
            raise ValidationError(_("Only the last review phase may be open-ended."))
        if not next_phase.start:
            raise ValidationError(
                _("All review phases except for the first one need a start date.")
            )
        if phase.end > next_phase.start:
            raise ValidationError(
                _(
                    "The review phases '{phase1}' and '{phase2}' overlap. "
                    "Please make sure that review phases do not overlap, then save again."
                ).format(phase1=phase.name, phase2=next_phase.name)
            )


def activate_review_phase(phase, *, person=None):
    phase.event.review_phases.update(is_active=False)
    phase.is_active = True
    phase.save()
    phase.log_action(
        ".activate", person=person, orga=person is not None, data={"name": phase.name}
    )


def _is_within_window(phase, _now):
    return (phase.start is None or phase.start <= _now) and (
        phase.end is None or phase.end >= _now
    )


def update_review_phase(event):
    """Advance ``event`` to the next review phase if the current one has
    ended (or has not started yet).

    Returns the now-active phase, or ``None`` when no phase is active.
    """
    _now = now()
    phase = event.active_review_phase
    if phase:
        if _is_within_window(phase, _now):
            return phase
        phase.is_active = False
        phase.save()
    next_phase = next(
        (p for p in event.review_phases.all() if _is_within_window(p, _now)), None
    )
    if next_phase:
        activate_review_phase(next_phase)
        return next_phase
