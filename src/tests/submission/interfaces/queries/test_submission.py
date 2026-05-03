# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.submission.interfaces.queries.submission import (
    annotate_assigned_reviews,
    reviewable_submissions_for_user,
    submissions_for_reviewer,
    submissions_for_user,
    unreviewed_submissions_for_user,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def make_reviewer(event):
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    user = UserFactory()
    team.members.add(user)
    return user


def test_annotate_assigned_reviews():
    event = EventFactory()
    user = UserFactory()
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)
    s1.assigned_reviewers.add(user)

    with scope(event=event):
        qs = annotate_assigned_reviews(event.submissions.all(), event, user)
        assigned = {s.pk: s.is_assigned for s in qs}

    assert assigned[s1.pk] is True
    assert assigned[s2.pk] is False


def test_submissions_for_reviewer_excludes_own_submissions():
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    own_sub = SubmissionFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    own_sub.speakers.add(speaker)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        qs = submissions_for_reviewer(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert own_sub.pk not in result_pks
    assert other_sub.pk in result_pks


def test_submissions_for_reviewer_assigned_visibility():
    event = EventFactory()
    user = UserFactory()
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)
    s1.assigned_reviewers.add(user)
    event.review_phases.filter(is_active=True).update(proposal_visibility="assigned")

    with scope(event=event):
        qs = submissions_for_reviewer(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk not in result_pks


def test_submissions_for_reviewer_track_restriction():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.limit_tracks.add(track1)
    user = UserFactory()
    team.members.add(user)
    s1 = SubmissionFactory(event=event, track=track1)
    s2 = SubmissionFactory(event=event, track=track2)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        qs = submissions_for_reviewer(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk not in result_pks


def test_submissions_for_reviewer_no_phase_returns_empty():
    event = EventFactory()
    event.review_phases.all().update(is_active=False)
    user = UserFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        qs = submissions_for_reviewer(event.submissions.all(), event, user)
    assert qs.count() == 0


def test_submissions_for_user_organiser():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)

    with scope(event=event):
        result = submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk in result_pks


def test_submissions_for_user_reviewer():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        result = submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert submission.pk in result_pks


def test_submissions_for_user_anonymous_with_schedule():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    released = ScheduleFactory(event=submission.event, version="v1")
    TalkSlotFactory(submission=submission, schedule=released, is_visible=True)

    with scope(event=submission.event):
        result = submissions_for_user(submission.event, AnonymousUser())

    assert submission.pk in set(result.values_list("pk", flat=True))


def test_submissions_for_user_anonymous_no_schedule():
    event = EventFactory(is_public=False)
    SubmissionFactory(event=event)

    with scope(event=event):
        result = submissions_for_user(event, AnonymousUser())

    assert result.count() == 0


def test_submissions_for_user_authenticated_no_permissions():
    event = EventFactory(is_public=False)
    user = UserFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        result = submissions_for_user(event, user)

    assert result.count() == 0


def test_submissions_for_user_review_context_pure_orga_excludes_own():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event, user=user)
    own_sub = SubmissionFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    own_sub.speakers.add(speaker)

    with scope(event=event):
        result_pks = set(
            submissions_for_user(event, user, review_context=True).values_list(
                "pk", flat=True
            )
        )

    assert own_sub.pk not in result_pks
    assert other_sub.pk in result_pks


def test_submissions_for_user_review_context_only_reviewer_applies_phase():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="assigned")

    with scope(event=event):
        result_pks = set(
            submissions_for_user(event, user, review_context=True).values_list(
                "pk", flat=True
            )
        )

    # Assigned visibility + no assignment → reviewer sees nothing
    assert submission.pk not in result_pks


def test_submissions_for_user_review_context_hybrid_respects_reviewer_perms():
    """A user with both orga and reviewer team membership is subject to review
    phase restrictions in a review context, even though without review_context
    they see everything as an orga."""
    event = EventFactory()
    orga_team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    track = TrackFactory(event=event)
    reviewer_team.limit_tracks.add(track)
    user = UserFactory()
    orga_team.members.add(user)
    reviewer_team.members.add(user)
    in_track = SubmissionFactory(event=event, track=track)
    other_track = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        # Without review_context: full orga visibility, no track restriction.
        full_pks = set(submissions_for_user(event, user).values_list("pk", flat=True))
        review_pks = set(
            submissions_for_user(event, user, review_context=True).values_list(
                "pk", flat=True
            )
        )

    assert in_track.pk in full_pks
    assert other_track.pk in full_pks
    assert in_track.pk in review_pks
    assert other_track.pk not in review_pks


def test_reviewable_submissions_for_user():
    event = EventFactory()
    user = make_reviewer(event)
    s1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        result = reviewable_submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk in result_pks


def test_unreviewed_submissions_for_user():
    event = EventFactory()
    user = make_reviewer(event)
    s1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=s1, user=user)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        result = unreviewed_submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk not in result_pks
    assert s2.pk in result_pks


def test_reviewable_submissions_for_user_is_randomised():
    """Calling reviewable_submissions_for_user repeatedly returns submissions
    in varying order, proving the queryset is not deterministic."""
    event = EventFactory()
    user = make_reviewer(event)
    SubmissionFactory.create_batch(6, event=event, state=SubmissionStates.SUBMITTED)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        orderings = set()
        for _ in range(20):
            pks = tuple(
                reviewable_submissions_for_user(event, user).values_list(
                    "pk", flat=True
                )
            )
            orderings.add(pks)

    assert len(orderings) > 1


def test_reviewable_submissions_for_user_prioritises_fewer_reviews():
    """Submissions with fewer reviews always come before those with more,
    even though the ordering within a tier is random."""
    event = EventFactory()
    reviewer = make_reviewer(event)
    other_user = UserFactory()
    s_zero = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s_one = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=s_one, user=other_user)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        result = list(
            reviewable_submissions_for_user(event, reviewer).values_list(
                "pk", flat=True
            )
        )

    assert result.index(s_zero.pk) < result.index(s_one.pk)


def test_reviewable_submissions_for_user_prioritises_assigned():
    """Assigned submissions come before unassigned ones regardless of review
    count."""
    event = EventFactory()
    reviewer = make_reviewer(event)
    s_unassigned = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s_assigned = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s_assigned.assigned_reviewers.add(reviewer)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        result = list(
            reviewable_submissions_for_user(event, reviewer).values_list(
                "pk", flat=True
            )
        )

    assert result.index(s_assigned.pk) < result.index(s_unassigned.pk)


def test_reviewable_submissions_for_user_randomises_within_same_review_count():
    """Three submissions with 0 reviews and three with 1 review: the 0-review
    tier always comes first, but within each tier the order varies."""
    event = EventFactory()
    reviewer = make_reviewer(event)
    other_user = UserFactory()
    zero_review = set()
    for _ in range(3):
        s = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        zero_review.add(s.pk)
    one_review = set()
    for _ in range(3):
        s = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        ReviewFactory(submission=s, user=other_user)
        one_review.add(s.pk)
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_review=True
    )

    with scope(event=event):
        orderings = set()
        for _ in range(20):
            pks = tuple(
                reviewable_submissions_for_user(event, reviewer).values_list(
                    "pk", flat=True
                )
            )
            orderings.add(pks)
            assert set(pks[:3]) == zero_review
            assert set(pks[3:]) == one_review

    assert len(orderings) > 1
