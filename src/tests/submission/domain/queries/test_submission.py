# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.schedule.models import TalkSlot
from pretalx.submission.domain.queries.submission import (
    annotate_assigned_reviews,
    annotate_confirmed_signup_count,
    annotate_requires_signup,
    annotate_slot_signup_status,
    annotate_submission_count,
    annotate_submission_signup_status,
    featured_submissions,
    filter_submissions_by_state,
    has_featured_submissions,
    information_for_user,
    reviewable_submissions_for_user,
    search_submissions,
    signed_up_submissions_for_user,
    sorted_speakers_prefetch,
    submissions_for_reviewer,
    submissions_for_user,
    talks_for_event,
    unreviewed_submissions_for_user,
)
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    AttendeeProfileFactory,
    AttendeeSignupFactory,
    EventFactory,
    ReviewFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_published_schedule

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
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)
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
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)
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


def test_submissions_for_reviewer_anonymous_returns_empty():
    event = EventFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        qs = submissions_for_reviewer(event.submissions.all(), event, AnonymousUser())

    assert qs.count() == 0


def test_submissions_for_reviewer_non_reviewer_returns_empty():
    event = EventFactory()
    user = UserFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        qs = submissions_for_reviewer(event.submissions.all(), event, user)

    assert qs.count() == 0


def test_submissions_for_reviewer_no_phase_returns_empty():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    user = make_reviewer(event)
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


def test_submissions_for_user_track_limited_reviewer_with_extra_permission():
    event = EventFactory()
    in_track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        # An unrelated permission must not lift reviewer track isolation.
        can_change_event_settings=True,
    )
    team.limit_tracks.add(in_track)
    user = UserFactory()
    team.members.add(user)
    visible = SubmissionFactory(event=event, track=in_track)
    hidden = SubmissionFactory(event=event, track=other_track)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        result_pks = set(submissions_for_user(event, user).values_list("pk", flat=True))

    assert result_pks == {visible.pk}
    assert hidden.pk not in result_pks


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


def test_submissions_for_user_public_event_without_released_schedule():
    event = EventFactory(is_public=True)
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


def test_filter_submissions_by_state_only_states():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    with scope(event=event):
        result = set(
            filter_submissions_by_state(event.submissions.all(), ["submitted"])
        )

    assert result == {submitted}


def test_filter_submissions_by_state_only_pending():
    event = EventFactory()
    pending = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        result = set(
            filter_submissions_by_state(
                event.submissions.all(), ["pending_state__accepted"]
            )
        )

    assert result == {pending}


def test_filter_submissions_by_state_mixed():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    pending = SubmissionFactory(
        event=event,
        state=SubmissionStates.REJECTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

    with scope(event=event):
        result = set(
            filter_submissions_by_state(
                event.submissions.all(), ["submitted", "pending_state__accepted"]
            )
        )

    assert result == {submitted, pending}


def test_filter_submissions_by_state_empty_filter_returns_all():
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    with scope(event=event):
        result = set(filter_submissions_by_state(event.submissions.all(), []))

    assert result == {sub}


def test_search_submissions_empty_query_returns_unchanged():
    event = EventFactory()
    sub = SubmissionFactory(event=event, title="Anything")

    with scope(event=event):
        result = set(
            search_submissions(event.submissions.all(), "", can_view_speakers=True)
        )

    assert result == {sub}


def test_search_submissions_anonymised_finds_redacted_value():
    event = EventFactory()
    redacted = SubmissionFactory(
        event=event,
        title="Original Title",
        anonymised={"_anonymised": True, "title": "Redacted Keyword"},
    )
    SubmissionFactory(event=event, title="Other")

    with scope(event=event):
        result = set(
            search_submissions(
                event.submissions.all(), "Redacted", can_view_speakers=False
            )
        )

    assert result == {redacted}


def test_search_submissions_anonymised_skips_original_for_redacted_field():
    """A redacted field's original value must not match for anonymous searchers."""
    event = EventFactory()
    SubmissionFactory(
        event=event,
        title="SecretOriginal",
        anonymised={"_anonymised": True, "title": "Redacted"},
    )

    with scope(event=event):
        result = set(
            search_submissions(
                event.submissions.all(), "SecretOriginal", can_view_speakers=False
            )
        )

    assert result == set()


def test_search_submissions_anonymised_searches_original_for_unredacted_field():
    """When a submission is anonymised but a particular field is not in the
    redaction set, the original value of that field remains searchable."""
    event = EventFactory()
    sub = SubmissionFactory(
        event=event,
        title="Original Title",
        abstract="UniqueAbstractKeyword",
        anonymised={"_anonymised": True, "title": "Redacted Title"},
    )

    with scope(event=event):
        result = set(
            search_submissions(
                event.submissions.all(),
                "UniqueAbstractKeyword",
                can_view_speakers=False,
                fulltext=True,
            )
        )

    assert result == {sub}


def test_sorted_speakers_prefetch_orders_by_position(django_assert_num_queries):
    submission = SubmissionFactory()
    first = SpeakerFactory(event=submission.event)
    second = SpeakerFactory(event=submission.event)
    third = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=first, position=2)
    SpeakerRoleFactory(submission=submission, speaker=second, position=0)
    SpeakerRoleFactory(submission=submission, speaker=third, position=1)

    with scope(event=submission.event):
        qs = Submission.objects.prefetch_related(sorted_speakers_prefetch())
        with django_assert_num_queries(2):
            sub = qs.get(pk=submission.pk)
            result = list(sub.sorted_speakers)

    assert result == [second, third, first]


def test_sorted_speakers_prefetch_with_prefix(django_assert_num_queries):
    """The ``submission__`` prefix lets slot querysets reuse the same prefetch."""
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    first = SpeakerFactory(event=submission.event)
    second = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=first, position=1)
    SpeakerRoleFactory(submission=submission, speaker=second, position=0)
    schedule = ScheduleFactory(event=submission.event, version="v1")
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=submission.event):
        qs = TalkSlot.objects.filter(pk=slot.pk).prefetch_related(
            sorted_speakers_prefetch("submission__")
        )
        fetched = qs.get(pk=slot.pk)
        result = list(fetched.submission.sorted_speakers)

    assert result == [second, first]


def test_submission_queryset_with_sorted_speakers_uses_prefetch(
    django_assert_num_queries,
):
    """``Submission.objects.with_sorted_speakers()`` is the public wrapper for
    ``sorted_speakers_prefetch`` and should serve speakers from the prefetch
    cache rather than issuing a fresh query for each submission."""
    submission = SubmissionFactory()
    first = SpeakerFactory(event=submission.event)
    second = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=first, position=1)
    SpeakerRoleFactory(submission=submission, speaker=second, position=0)

    with scope(event=submission.event):
        qs = Submission.objects.with_sorted_speakers()
        with django_assert_num_queries(2):
            sub = qs.get(pk=submission.pk)
            result = list(sub.sorted_speakers)

    assert result == [second, first]


def test_talk_slot_queryset_with_sorted_speakers_uses_prefetch(
    django_assert_num_queries,
):
    """``TalkSlot.objects.with_sorted_speakers()`` mirrors the submission
    queryset wrapper but reaches through ``submission__speakers``."""
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    first = SpeakerFactory(event=submission.event)
    second = SpeakerFactory(event=submission.event)
    SpeakerRoleFactory(submission=submission, speaker=first, position=1)
    SpeakerRoleFactory(submission=submission, speaker=second, position=0)
    schedule = ScheduleFactory(event=submission.event, version="v1")
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=submission.event):
        qs = TalkSlot.objects.filter(pk=slot.pk).with_sorted_speakers()
        fetched = qs.get(pk=slot.pk)
        result = list(fetched.submission.sorted_speakers)

    assert result == [second, first]


@pytest.mark.parametrize("user", (None, AnonymousUser()), ids=["none", "anonymous"])
def test_information_for_user_anonymous_returns_empty(user):
    event = EventFactory()
    SpeakerInformationFactory(event=event, target_group="submitters")
    assert list(information_for_user(event, user)) == []


def test_information_for_user_submitters_without_submission():
    event = EventFactory()
    user = UserFactory()
    SpeakerInformationFactory(event=event, target_group="submitters")
    assert list(information_for_user(event, user)) == []


@pytest.mark.parametrize(
    ("target_group", "state", "expected"),
    (
        ("submitters", SubmissionStates.SUBMITTED, True),
        ("confirmed", SubmissionStates.CONFIRMED, True),
        ("confirmed", SubmissionStates.SUBMITTED, False),
        ("accepted", SubmissionStates.ACCEPTED, True),
        ("accepted", SubmissionStates.SUBMITTED, False),
    ),
)
def test_information_for_user_matches_target_group_to_submission_state(
    target_group, state, expected
):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=state)
    submission.speakers.add(speaker)
    info = SpeakerInformationFactory(event=event, target_group=target_group)

    visible = list(information_for_user(event, speaker.user))
    assert (info in visible) is expected


def test_information_for_user_limited_to_track():
    """Info limited to a track is visible only to speakers on that track."""
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    submission.speakers.add(speaker)
    info = SpeakerInformationFactory(event=event, target_group="submitters")
    info.limit_tracks.add(track)

    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event, track=other_track)
    other_submission.speakers.add(other_speaker)

    assert list(information_for_user(event, speaker.user)) == [info]
    assert list(information_for_user(event, other_speaker.user)) == []


def test_talks_for_event_returns_slotted_submissions_in_current_schedule():
    event = EventFactory()
    [in_schedule] = make_published_schedule(event, item_count=1)
    # An accepted-but-not-scheduled submission must not leak into talks().
    with scope(event=event):
        SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    with scope(event=event):
        result = list(talks_for_event(event))

    assert result == [in_schedule]


def test_talks_for_event_no_released_schedule_returns_none():
    """Before the first release, talks_for_event yields an empty queryset
    even when slots exist on the WIP schedule."""
    event = EventFactory()
    with scope(event=event):
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=sub)

    with scope(event=event):
        assert list(talks_for_event(event)) == []


def test_talks_for_event_empty_schedule_returns_empty():
    """A released schedule with no scheduled talks yields an empty queryset."""
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")
    with scope(event=event):
        SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    with scope(event=event):
        assert list(talks_for_event(event)) == []


def test_information_for_user_limited_to_type():
    """Info limited to a type is visible only to speakers on that type."""
    event = EventFactory()
    other_type = SubmissionTypeFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    info = SpeakerInformationFactory(event=event, target_group="submitters")
    info.limit_types.add(submission.submission_type)

    other_speaker = SpeakerFactory(event=event)
    other_submission = SubmissionFactory(event=event, submission_type=other_type)
    other_submission.speakers.add(other_speaker)

    assert list(information_for_user(event, speaker.user)) == [info]
    assert list(information_for_user(event, other_speaker.user)) == []


def test_featured_submissions_excludes_unfeatured():
    event = EventFactory()
    with scope(event=event):
        featured = SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
        SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )

        assert list(featured_submissions(event)) == [featured]


@pytest.mark.parametrize(
    "state",
    (SubmissionStates.REJECTED, SubmissionStates.CANCELED, SubmissionStates.WITHDRAWN),
)
def test_featured_submissions_excludes_hidden_states(state):
    event = EventFactory()
    with scope(event=event):
        SubmissionFactory(event=event, is_featured=True, state=state)

        assert list(featured_submissions(event)) == []


def test_featured_submissions_orders_by_title():
    event = EventFactory()
    with scope(event=event):
        b = SubmissionFactory(
            event=event, title="B", is_featured=True, state=SubmissionStates.CONFIRMED
        )
        a = SubmissionFactory(
            event=event, title="A", is_featured=True, state=SubmissionStates.CONFIRMED
        )

        assert list(featured_submissions(event)) == [a, b]


def test_has_featured_submissions_true():
    event = EventFactory()
    with scope(event=event):
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )

        assert has_featured_submissions(event) is True


def test_has_featured_submissions_false_when_only_unfeatured():
    event = EventFactory()
    with scope(event=event):
        SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )

        assert has_featured_submissions(event) is False


@pytest.mark.parametrize(
    "state",
    (SubmissionStates.REJECTED, SubmissionStates.CANCELED, SubmissionStates.WITHDRAWN),
)
def test_has_featured_submissions_excludes_hidden_states(state):
    event = EventFactory()
    with scope(event=event):
        SubmissionFactory(event=event, is_featured=True, state=state)

        assert has_featured_submissions(event) is False


def test_annotate_submission_count_counts_non_draft_only():
    event = EventFactory()
    track = TrackFactory(event=event)
    with scope(event=event):
        SubmissionFactory(event=event, track=track, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, track=track, state=SubmissionStates.DRAFT)

        result = annotate_submission_count(event.tracks.all()).get(pk=track.pk)
        assert result.submission_count == 1


def test_annotate_submission_count_zero_for_unused():
    event = EventFactory()
    track = TrackFactory(event=event)

    with scope(event=event):
        result = annotate_submission_count(event.tracks.all()).get(pk=track.pk)
        assert result.submission_count == 0


@pytest.mark.parametrize(
    ("submission_override", "track_required", "type_required", "expected"),
    (
        (True, False, False, True),
        (False, True, True, False),
        (None, True, False, True),
        (None, False, True, True),
        (None, True, True, True),
        (None, False, False, False),
    ),
    ids=(
        "submission_override_true_wins",
        "submission_override_false_wins",
        "track_only",
        "type_only",
        "both_track_and_type",
        "nothing_required",
    ),
)
def test_annotate_requires_signup_respects_override_and_inheritance(
    submission_override, track_required, type_required, expected
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    track = TrackFactory(event=event, attendee_signup_required=track_required)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        track=track,
        attendee_signup_required=submission_override,
    )

    with scope(event=event):
        annotated = annotate_requires_signup(event.submissions.all()).get(
            pk=submission.pk
        )

    assert annotated._annotated_requires_signup is expected


def test_annotate_requires_signup_without_track():
    """Submissions without a track only consider the submission type setting."""
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type, track=None)

    with scope(event=event):
        annotated = annotate_requires_signup(event.submissions.all()).get(
            pk=submission.pk
        )

    assert annotated._annotated_requires_signup is True


def test_annotate_requires_signup_is_idempotent():
    event = EventFactory()
    submission = SubmissionFactory(event=event, attendee_signup_required=True)

    with scope(event=event):
        annotated = annotate_requires_signup(
            annotate_requires_signup(event.submissions.all())
        ).get(pk=submission.pk)

    assert annotated._annotated_requires_signup is True


def test_annotate_confirmed_signup_count_counts_only_confirmed():
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CONFIRMED
        )
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CONFIRMED
        )
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CANCELED
        )

        annotated = annotate_confirmed_signup_count(event.submissions.all()).get(
            pk=submission.pk
        )

    assert annotated._annotated_confirmed_signup_count == 2


def test_annotate_confirmed_signup_count_zero_for_no_signups():
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        annotated = annotate_confirmed_signup_count(event.submissions.all()).get(
            pk=submission.pk
        )

    assert annotated._annotated_confirmed_signup_count == 0


def test_annotate_confirmed_signup_count_is_idempotent():
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CONFIRMED
        )
        annotated = annotate_confirmed_signup_count(
            annotate_confirmed_signup_count(event.submissions.all())
        ).get(pk=submission.pk)

    assert annotated._annotated_confirmed_signup_count == 1


@pytest.mark.parametrize(
    (
        "requires_signup",
        "room_capacity",
        "override_capacity",
        "confirmed",
        "canceled",
        "expected",
    ),
    (
        (False, 10, None, 0, 0, None),
        (True, 10, None, 0, 0, "open"),
        (True, 2, None, 2, 0, "full"),
        (True, 100, 1, 1, 0, "full"),
        (True, None, None, 5, 0, "open"),
        (True, 2, None, 1, 2, "open"),
    ),
    ids=(
        "non_signup_session_resolves_to_none",
        "open_with_room_capacity",
        "full_at_room_capacity",
        "full_uses_submission_override_capacity",
        "open_when_capacity_unknown",
        "ignores_canceled_signups",
    ),
)
def test_annotate_slot_signup_status(
    requires_signup, room_capacity, override_capacity, confirmed, canceled, expected
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=requires_signup
    )
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        attendee_signup_capacity=override_capacity,
    )
    with scope(event=event):
        slot = TalkSlotFactory(
            submission=submission, schedule=event.wip_schedule, room=room
        )
        for _ in range(confirmed):
            AttendeeSignupFactory(submission=submission)
        for _ in range(canceled):
            AttendeeSignupFactory(
                submission=submission, state=AttendeeSignupStates.CANCELED
            )

        annotated = annotate_slot_signup_status(
            TalkSlot.objects.filter(pk=slot.pk)
        ).get()

    # Non-signup sessions resolve to NULL on the annotated queryset; callers
    # use ``hasattr`` to detect "annotation present, value None".
    assert hasattr(annotated, "_annotated_signup_status")
    assert annotated._annotated_signup_status == expected


def test_annotate_submission_signup_status_none_for_non_signup_session():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        annotated = annotate_submission_signup_status(
            event.submissions.all(), event.current_schedule
        ).get(pk=submission.pk)

    # Non-signup sessions resolve to NULL on the annotated queryset; callers
    # use ``hasattr`` to detect "annotation present, value None".
    assert hasattr(annotated, "_annotated_signup_status")
    assert annotated._annotated_signup_status is None


def test_annotate_submission_signup_status_full_uses_override():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=1
    )
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)
        annotated = annotate_submission_signup_status(
            event.submissions.all(), event.current_schedule
        ).get(pk=submission.pk)

    assert annotated._annotated_signup_status == "full"


def test_annotate_submission_signup_status_full_uses_room_capacity_from_schedule():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    room = RoomFactory(event=event, capacity=1)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    schedule = ScheduleFactory(event=event, version="v1")
    with scope(event=event):
        TalkSlotFactory(submission=submission, schedule=schedule, room=room)
        AttendeeSignupFactory(submission=submission)
        # ``current_schedule`` is the latest released schedule.
        annotated = annotate_submission_signup_status(
            event.submissions.all(), event.current_schedule
        ).get(pk=submission.pk)

    assert annotated._annotated_signup_status == "full"


def test_annotate_submission_signup_status_open_without_schedule():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scope(event=event):
        annotated = annotate_submission_signup_status(
            event.submissions.all(), None
        ).get(pk=submission.pk)

    # No override, no schedule → capacity unknown → status "open".
    assert annotated._annotated_signup_status == "open"


def test_annotate_slot_signup_status_is_idempotent():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scope(event=event):
        TalkSlotFactory(submission=submission, schedule=event.wip_schedule)
        queryset = annotate_slot_signup_status(
            annotate_slot_signup_status(TalkSlot.objects.filter(submission=submission))
        )
        annotated = queryset.get()

    assert annotated._annotated_signup_status == "open"


def test_annotate_submission_signup_status_is_idempotent():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scope(event=event):
        queryset = annotate_submission_signup_status(
            annotate_submission_signup_status(
                event.submissions.all(), event.current_schedule
            ),
            event.current_schedule,
        )
        annotated = queryset.get(pk=submission.pk)

    assert annotated._annotated_signup_status == "open"


def _make_visible_submission(event):
    """Submission with a visible slot in a released schedule for ``event``.

    ``signed_up_submissions_for_user`` reuses ``submissions_for_user``'s
    visibility scope, so attendees only see submissions that the released
    schedule already exposes; this helper sets up that precondition for
    tests that want to isolate the signup-row filter from visibility.
    """
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    released = ScheduleFactory(event=event, version="v1")
    TalkSlotFactory(submission=submission, schedule=released, is_visible=True)
    return submission


def test_signed_up_submissions_for_user_anonymous_returns_empty():
    event = EventFactory()
    _make_visible_submission(event)
    with scope(event=event):
        result = signed_up_submissions_for_user(event, AnonymousUser())
    assert result.count() == 0


def test_signed_up_submissions_for_user_includes_confirmed_signup():
    event = EventFactory()
    user = UserFactory()
    submission = _make_visible_submission(event)
    with scope(event=event):
        profile = AttendeeProfileFactory(user=user, event=event)
        AttendeeSignupFactory(submission=submission, attendee=profile)
        result = signed_up_submissions_for_user(event, user)
    assert list(result.values_list("pk", flat=True)) == [submission.pk]


def test_signed_up_submissions_for_user_excludes_cancelled_signup():
    event = EventFactory()
    user = UserFactory()
    submission = _make_visible_submission(event)
    with scope(event=event):
        profile = AttendeeProfileFactory(user=user, event=event)
        AttendeeSignupFactory(
            submission=submission, attendee=profile, state=AttendeeSignupStates.CANCELED
        )
        result = signed_up_submissions_for_user(event, user)
    assert result.count() == 0


def test_signed_up_submissions_for_user_excludes_other_users_signups():
    event = EventFactory()
    user = UserFactory()
    other_user = UserFactory()
    submission = _make_visible_submission(event)
    with scope(event=event):
        other_profile = AttendeeProfileFactory(user=other_user, event=event)
        AttendeeSignupFactory(submission=submission, attendee=other_profile)
        result = signed_up_submissions_for_user(event, user)
    assert result.count() == 0


def test_signed_up_submissions_for_user_respects_visibility_scope():
    """A signup on an unreleased submission stays hidden for plain attendees.

    Confirms that ``signed_up_submissions_for_user`` keeps inheriting the
    released-schedule gate from ``submissions_for_user``: signing up does not
    grant a side-channel into submissions the user otherwise could not see.
    """
    event = EventFactory()
    user = UserFactory()
    # Submission exists but no released schedule / visible slot.
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        profile = AttendeeProfileFactory(user=user, event=event)
        AttendeeSignupFactory(submission=submission, attendee=profile)
        result = signed_up_submissions_for_user(event, user)
    assert result.count() == 0
