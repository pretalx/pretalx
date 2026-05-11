# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.timezone import now


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


def activate_review_phase(phase, *, person=None):
    phase.event.review_phases.all().update(is_active=False)
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
