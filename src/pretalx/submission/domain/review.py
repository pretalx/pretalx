# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


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
