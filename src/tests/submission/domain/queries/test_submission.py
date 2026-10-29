# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope, scopes_disabled

from pretalx.person.models import SpeakerProfile
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.models import Schedule, TalkSlot
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
    search_speakers,
    search_submissions,
    signed_up_submissions_for_user,
    sorted_speakers_prefetch,
    submissions_for_reviewer,
    submissions_for_user,
    talks_for_event,
    talks_for_schedule,
    unreviewed_submissions_for_user,
)
from pretalx.submission.enums import AttendeeSignupStates, SubmissionContext
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
from tests.utils import make_published_schedule, refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _team_user(event, **team_kwargs):
    team = TeamFactory(organiser=event.organiser, all_events=True, **team_kwargs)
    user = UserFactory()
    team.members.add(user)
    return user, team


def make_reviewer(event):
    return _team_user(event, is_reviewer=True)[0]


def _set_phase(event, **fields):
    event.review_phases.filter(is_active=True).update(**fields)
    event.__dict__.pop("active_review_phase", None)


def _pks(queryset):
    return set(queryset.values_list("pk", flat=True))


def test_submissions_for_reviewer_visibility():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    user, team = _team_user(event, is_reviewer=True)
    team.limit_tracks.add(track1)
    own = SubmissionFactory(event=event, track=track1)
    own.speakers.add(SpeakerFactory(event=event, user=user))
    plain = SubmissionFactory(event=event, track=track1)
    other_track = SubmissionFactory(event=event, track=track2)
    assigned = SubmissionFactory(event=event, track=track1)
    assigned.assigned_reviewers.add(user)

    with scope(event=event):
        submissions = event.submissions.all()
        assert {
            s.pk: s.is_assigned
            for s in annotate_assigned_reviews(submissions, event, user)
        } == {own.pk: False, plain.pk: False, other_track.pk: False, assigned.pk: True}

        _set_phase(event, proposal_visibility="all")
        assert _pks(submissions_for_reviewer(submissions, event, user)) == {
            plain.pk,
            assigned.pk,
        }
        assert not submissions_for_reviewer(submissions, event, UserFactory())

        _set_phase(event, proposal_visibility="assigned")
        assert _pks(submissions_for_reviewer(submissions, event, user)) == {assigned.pk}

        assert not submissions_for_reviewer(submissions, event, AnonymousUser())

        _set_phase(event, is_active=False)
        assert not submissions_for_reviewer(submissions, event, user)


def test_submissions_for_user_by_role_and_context():
    event = EventFactory()
    track = TrackFactory(event=event)
    orga, _ = _team_user(event, can_change_submissions=True)
    # An unrelated permission must not lift reviewer track isolation.
    reviewer, reviewer_team = _team_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=True,
    )
    reviewer_team.limit_tracks.add(track)
    hybrid, _ = _team_user(event, can_change_submissions=True)
    reviewer_team.members.add(hybrid)
    plain_user = UserFactory()
    own = SubmissionFactory(event=event)
    own.speakers.add(SpeakerFactory(event=event, user=orga))
    in_track = SubmissionFactory(event=event, track=track)
    other_track = SubmissionFactory(event=event, track=TrackFactory(event=event))
    everything = {own.pk, in_track.pk, other_track.pk}
    _set_phase(event, proposal_visibility="all")

    with scope(event=event):
        assert _pks(submissions_for_user(event, orga)) == everything
        assert _pks(
            submissions_for_user(event, orga, context=SubmissionContext.REVIEW)
        ) == {in_track.pk, other_track.pk}
        assert _pks(submissions_for_user(event, reviewer)) == {in_track.pk}
        assert _pks(submissions_for_user(event, hybrid)) == everything
        assert _pks(
            submissions_for_user(event, hybrid, context=SubmissionContext.REVIEW)
        ) == {in_track.pk}
        assert not submissions_for_user(event, plain_user)
        assert not submissions_for_user(event, AnonymousUser())
        assert not submissions_for_user(event, orga, context=SubmissionContext.PUBLIC)

        # Assigned visibility + no assignment → reviewer sees nothing
        _set_phase(event, proposal_visibility="assigned")
        assert not submissions_for_user(
            event, reviewer, context=SubmissionContext.REVIEW
        )

    (talk,) = make_published_schedule(event, 1)
    _set_phase(event, is_active=False)
    # Permission checks cache on the user, so rebuild every instance.
    event = refresh(event)
    with scope(event=event):
        assert _pks(submissions_for_user(event, AnonymousUser())) == {talk.pk}
        assert _pks(submissions_for_user(event, refresh(plain_user))) == {talk.pk}
        for user in (orga, reviewer, hybrid):
            assert _pks(
                submissions_for_user(
                    event, refresh(user), context=SubmissionContext.PUBLIC
                )
            ) == {talk.pk}


def test_reviewable_submissions_for_user_order_and_exclusions():
    event = EventFactory()
    reviewer = make_reviewer(event)
    assigned = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assigned.assigned_reviewers.add(reviewer)
    unreviewed = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    reviewed_by_other = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=reviewed_by_other, user=UserFactory())
    reviewed_by_me = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=reviewed_by_me, user=reviewer)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    for pending in (SubmissionStates.ACCEPTED, SubmissionStates.REJECTED):
        SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, pending_state=pending
        )
    _set_phase(event, proposal_visibility="all", can_review=True)

    with scope(event=event):
        result = list(
            reviewable_submissions_for_user(event, reviewer).values_list(
                "pk", flat=True
            )
        )
        assert result[:2] == [assigned.pk, unreviewed.pk]
        assert set(result[2:]) == {reviewed_by_other.pk, reviewed_by_me.pk}
        assert _pks(unreviewed_submissions_for_user(event, reviewer)) == {
            assigned.pk,
            unreviewed.pk,
            reviewed_by_other.pk,
        }


def test_reviewable_submissions_for_user_randomises_within_same_review_count():
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
    _set_phase(event, proposal_visibility="all", can_review=True)

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


def test_filter_submissions_by_state_mixes_states_and_pending_states():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    pending = SubmissionFactory(
        event=event,
        state=SubmissionStates.REJECTED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    rejected = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

    with scope(event=event):
        submissions = event.submissions.all()
        assert set(filter_submissions_by_state(submissions, ["submitted"])) == {
            submitted
        }
        assert set(
            filter_submissions_by_state(submissions, ["pending_state__accepted"])
        ) == {pending}
        assert set(
            filter_submissions_by_state(
                submissions, ["submitted", "pending_state__accepted"]
            )
        ) == {submitted, pending}
        assert set(filter_submissions_by_state(submissions, [])) == {
            submitted,
            pending,
            rejected,
        }


def test_search_submissions_honours_speaker_visibility_and_anonymisation():
    event = EventFactory()
    plain = SubmissionFactory(event=event, title="Plain")
    SpeakerRoleFactory(
        submission=plain,
        speaker=SpeakerFactory(
            event=event, name="Needle Speaker", email="hidden@example.org"
        ),
    )
    redacted = SubmissionFactory(
        event=event,
        title="Original Title",
        abstract="UniqueAbstractKeyword",
        anonymised={"_anonymised": True, "title": "Redacted Keyword"},
    )
    other = SubmissionFactory(event=event, title="Other")

    with scope(event=event):
        submissions = event.submissions.all()
        assert set(search_submissions(submissions, "", can_view_speakers=True)) == {
            plain,
            redacted,
            other,
        }
        assert set(
            search_submissions(submissions, "Needle", can_view_speakers=True)
        ) == {plain}
        assert not search_submissions(
            submissions, "hidden@example.org", can_view_speakers=True
        )
        assert set(
            search_submissions(submissions, "Redacted", can_view_speakers=False)
        ) == {redacted}
        assert not search_submissions(submissions, "Original", can_view_speakers=False)
        assert set(
            search_submissions(
                submissions,
                "UniqueAbstractKeyword",
                can_view_speakers=False,
                fulltext=True,
            )
        ) == {redacted}


def test_search_speakers_matches_effective_name_and_email():
    event = EventFactory()
    by_name = SpeakerFactory(event=event, name="Needle")
    by_user_name = SpeakerFactory(event=event, user__name="Needle")
    by_email = SpeakerFactory(event=event, email="needle@example.org")
    by_user_email = SpeakerFactory(event=event, user__email="needle@example.org")
    SpeakerFactory(
        event=event,
        name="Shown Name",
        email="shown@example.org",
        user__name="Needle",
        user__email="needle2@example.org",
    )
    SpeakerFactory(event=event, name="Other", user__name="Other")

    with scope(event=event):
        assert set(search_speakers(SpeakerProfile.objects.all(), "needle")) == {
            by_name,
            by_user_name,
            by_email,
            by_user_email,
        }
        assert set(
            search_speakers(SpeakerProfile.objects.all(), "needle", include_email=False)
        ) == {by_name, by_user_name}


def test_sorted_speakers_prefetch_orders_by_position(django_assert_num_queries):
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    first = SpeakerFactory(event=event)
    second = SpeakerFactory(event=event)
    third = SpeakerFactory(event=event)
    SpeakerRoleFactory(submission=submission, speaker=first, position=2)
    SpeakerRoleFactory(submission=submission, speaker=second, position=0)
    SpeakerRoleFactory(submission=submission, speaker=third, position=1)
    schedule = ScheduleFactory(event=event, version="v1")
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=event):
        qs = Submission.objects.prefetch_related(sorted_speakers_prefetch())
        with django_assert_num_queries(2):
            assert list(qs.get(pk=submission.pk).sorted_speakers) == [
                second,
                third,
                first,
            ]
        with django_assert_num_queries(2):
            assert list(
                Submission.objects.with_sorted_speakers()
                .get(pk=submission.pk)
                .sorted_speakers
            ) == [second, third, first]

        qs = TalkSlot.objects.filter(pk=slot.pk).prefetch_related(
            sorted_speakers_prefetch("submission__")
        )
        assert list(qs.get(pk=slot.pk).submission.sorted_speakers) == [
            second,
            third,
            first,
        ]
        qs = TalkSlot.objects.filter(pk=slot.pk).with_sorted_speakers()
        assert list(qs.get(pk=slot.pk).submission.sorted_speakers) == [
            second,
            third,
            first,
        ]


def test_information_for_user_matches_target_group_track_and_type():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_type = SubmissionTypeFactory(event=event)
    speakers = {}
    for key, kwargs in (
        ("submitted", {"state": SubmissionStates.SUBMITTED, "track": track}),
        ("accepted", {"state": SubmissionStates.ACCEPTED, "track": track}),
        ("confirmed", {"state": SubmissionStates.CONFIRMED, "track": track}),
        ("other_track", {"track": TrackFactory(event=event)}),
        ("other_type", {"submission_type": other_type, "track": track}),
    ):
        speakers[key] = SpeakerFactory(event=event)
        SubmissionFactory(event=event, **kwargs).speakers.add(speakers[key])
    submitters = SpeakerInformationFactory(event=event, target_group="submitters")
    accepted = SpeakerInformationFactory(event=event, target_group="accepted")
    confirmed = SpeakerInformationFactory(event=event, target_group="confirmed")
    by_track = SpeakerInformationFactory(event=event, target_group="submitters")
    by_track.limit_tracks.add(track)
    by_type = SpeakerInformationFactory(event=event, target_group="submitters")
    by_type.limit_types.add(event.cfp.default_type)

    assert list(information_for_user(event, None)) == []
    assert list(information_for_user(event, AnonymousUser())) == []
    assert list(information_for_user(event, UserFactory())) == []
    assert set(information_for_user(event, speakers["submitted"].user)) == {
        submitters,
        by_track,
        by_type,
    }
    assert set(information_for_user(event, speakers["accepted"].user)) == {
        submitters,
        accepted,
        by_track,
        by_type,
    }
    assert set(information_for_user(event, speakers["confirmed"].user)) == {
        submitters,
        accepted,
        confirmed,
        by_track,
        by_type,
    }
    assert set(information_for_user(event, speakers["other_track"].user)) == {
        submitters,
        by_type,
    }
    assert set(information_for_user(event, speakers["other_type"].user)) == {
        submitters,
        by_track,
    }


def test_talks_for_event_and_schedule_follow_released_visible_slots():
    event = EventFactory()
    with scope(event=event):
        unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=unscheduled, schedule=event.wip_schedule)
        assert list(talks_for_event(event)) == []
        # An accepted-but-not-scheduled submission must not leak into talks()
        unscheduled.slots.all().delete()

    [first] = make_published_schedule(event, item_count=1, version="v1")
    event = refresh(event)
    with scope(event=event):
        # Nor one whose slot was hidden at release time
        hidden = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(
            submission=hidden, schedule=event.current_schedule, is_visible=False
        )
        # A second slot must not duplicate the submission
        TalkSlotFactory(
            submission=first, schedule=event.current_schedule, is_visible=True
        )
        assert list(talks_for_event(event)) == [first]

    with scopes_disabled():
        second = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        second.speakers.add(SpeakerFactory(event=event))
        TalkSlotFactory(
            submission=second,
            is_visible=True,
            start=event.datetime_from + dt.timedelta(hours=5),
            end=event.datetime_from + dt.timedelta(hours=6),
        )
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert list(talks_for_schedule(v1)) == [first]
        assert set(talks_for_schedule(v2)) == {first, second}
        assert set(talks_for_event(refresh(event))) == {first, second}


def test_featured_submissions_excludes_hidden_states_and_orders_by_title():
    event = EventFactory()
    with scope(event=event):
        b = SubmissionFactory(
            event=event, title="B", is_featured=True, state=SubmissionStates.CONFIRMED
        )
        a = SubmissionFactory(
            event=event, title="A", is_featured=True, state=SubmissionStates.CONFIRMED
        )
        SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )
        for state in (
            SubmissionStates.REJECTED,
            SubmissionStates.CANCELED,
            SubmissionStates.WITHDRAWN,
        ):
            SubmissionFactory(event=event, is_featured=True, state=state)

        assert list(featured_submissions(event)) == [a, b]
        assert has_featured_submissions(event) is True

        event.submissions.filter(state=SubmissionStates.CONFIRMED).update(
            is_featured=False
        )

        assert list(featured_submissions(event)) == []
        assert has_featured_submissions(event) is False


def test_annotate_submission_count_counts_non_draft_only():
    event = EventFactory()
    track = TrackFactory(event=event)
    unused = TrackFactory(event=event)
    with scope(event=event):
        SubmissionFactory(event=event, track=track, state=SubmissionStates.SUBMITTED)
        SubmissionFactory(event=event, track=track, state=SubmissionStates.DRAFT)

        assert {
            row.pk: row.submission_count
            for row in annotate_submission_count(event.tracks.all())
        } == {track.pk: 1, unused.pk: 0}


@pytest.mark.parametrize(
    ("submission_override", "track_required", "type_required", "expected"),
    (
        (True, False, False, True),
        (False, True, True, False),
        (None, True, False, True),
        (None, False, True, True),
        (None, True, True, True),
        (None, False, False, False),
        (None, None, True, True),
    ),
    ids=(
        "submission_override_true_wins",
        "submission_override_false_wins",
        "track_only",
        "type_only",
        "both_track_and_type",
        "nothing_required",
        "without_track",
    ),
)
def test_annotate_requires_signup_respects_override_and_inheritance(
    submission_override, track_required, type_required, expected
):
    event = EventFactory()
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    track = (
        None
        if track_required is None
        else TrackFactory(event=event, attendee_signup_required=track_required)
    )
    submission = SubmissionFactory(
        event=event,
        submission_type=sub_type,
        track=track,
        attendee_signup_required=submission_override,
    )

    with scope(event=event):
        annotated = annotate_requires_signup(
            annotate_requires_signup(event.submissions.all())
        ).get(pk=submission.pk)

    assert annotated._annotated_requires_signup is expected


def test_annotate_confirmed_signup_count_counts_only_confirmed():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    unsigned = SubmissionFactory(event=event)

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

        assert {
            row.pk: row._annotated_confirmed_signup_count
            for row in annotate_confirmed_signup_count(
                annotate_confirmed_signup_count(event.submissions.all())
            )
        } == {submission.pk: 2, unsigned.pk: 0}


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
            annotate_slot_signup_status(TalkSlot.objects.filter(pk=slot.pk))
        ).get()

    # Non-signup sessions resolve to NULL on the annotated queryset; callers
    # use ``hasattr`` to detect "annotation present, value None".
    assert hasattr(annotated, "_annotated_signup_status")
    assert annotated._annotated_signup_status == expected


def test_annotate_submission_signup_status_resolves_capacity_from_schedule():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    no_signup = SubmissionFactory(event=event)
    override = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=1
    )
    by_room = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    open_session = SubmissionFactory(event=event, submission_type=sub_type)
    schedule = ScheduleFactory(event=event, version="v1")
    with scope(event=event):
        TalkSlotFactory(
            submission=by_room,
            schedule=schedule,
            room=RoomFactory(event=event, capacity=1),
        )
        AttendeeSignupFactory(submission=override)
        AttendeeSignupFactory(submission=by_room)

        # ``current_schedule`` is the latest released schedule.
        def statuses(current_schedule):
            queryset = annotate_submission_signup_status(
                annotate_submission_signup_status(
                    event.submissions.all(), current_schedule
                ),
                current_schedule,
            )
            return {row.pk: row._annotated_signup_status for row in queryset}

        assert statuses(event.current_schedule) == {
            no_signup.pk: None,
            override.pk: "full",
            by_room.pk: "full",
            open_session.pk: "open",
        }
        # No override, no schedule → capacity unknown → status "open".
        assert statuses(None) == {
            no_signup.pk: None,
            override.pk: "full",
            by_room.pk: "open",
            open_session.pk: "open",
        }


def test_signed_up_submissions_for_user_follows_public_visibility():
    event = EventFactory()
    user = UserFactory()
    other_user = UserFactory()
    reviewer, _ = _team_user(event, is_reviewer=True, can_change_submissions=False)
    visible = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    released = ScheduleFactory(event=event, version="v1")
    TalkSlotFactory(submission=visible, schedule=released, is_visible=True)
    _set_phase(event, is_active=False)

    with scope(event=event):
        profile = AttendeeProfileFactory(user=user, event=event)
        AttendeeSignupFactory(submission=visible, attendee=profile)
        AttendeeSignupFactory(submission=unscheduled, attendee=profile)
        AttendeeSignupFactory(
            submission=visible,
            attendee=AttendeeProfileFactory(user=reviewer, event=event),
        )
        AttendeeSignupFactory(
            submission=visible,
            attendee=AttendeeProfileFactory(user=other_user, event=event),
            state=AttendeeSignupStates.CANCELED,
        )

        assert not signed_up_submissions_for_user(event, AnonymousUser())
        assert _pks(signed_up_submissions_for_user(event, user)) == {visible.pk}
        assert _pks(signed_up_submissions_for_user(event, reviewer)) == {visible.pk}
        assert not signed_up_submissions_for_user(event, other_user)
        assert not signed_up_submissions_for_user(event, UserFactory())
