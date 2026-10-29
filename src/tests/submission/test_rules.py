# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.submission import rules
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("state", "withdrawn", "confirmed", "removed"),
    (
        ("submitted", True, False, True),
        ("accepted", True, True, True),
        ("rejected", False, False, True),
        ("confirmed", False, False, True),
        ("canceled", False, False, True),
        ("withdrawn", False, False, True),
        ("draft", False, False, False),
    ),
    ids=[
        "submitted",
        "accepted",
        "rejected",
        "confirmed",
        "canceled",
        "withdrawn",
        "draft",
    ],
)
def test_state_predicates(state, withdrawn, confirmed, removed):
    submission = Submission(state=state)

    assert rules.can_be_withdrawn(None, submission) is withdrawn
    assert rules.can_be_confirmed(None, submission) is confirmed
    assert rules.can_be_removed(None, submission) is removed


@pytest.mark.parametrize(
    "predicate",
    (
        rules.can_be_withdrawn,
        rules.can_be_confirmed,
        rules.can_be_removed,
        rules.can_be_edited,
        rules.can_be_reviewed,
        rules.is_speaker,
        rules.is_review_author,
        rules.is_comment_author,
    ),
    ids=[
        "can_be_withdrawn",
        "can_be_confirmed",
        "can_be_removed",
        "can_be_edited",
        "can_be_reviewed",
        "is_speaker",
        "is_review_author",
        "is_comment_author",
    ],
)
def test_predicate_returns_false_for_none(predicate):
    assert not predicate(None, None)


@pytest.mark.parametrize(
    ("editable", "expected"),
    ((True, True), (False, False)),
    ids=["editable", "not_editable"],
)
def test_can_be_edited(editable, expected):
    submission = Submission()
    submission.editable = editable
    assert rules.can_be_edited(None, submission) is expected


def test_can_be_reviewed_needs_submitted_state_and_open_phase():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    review = ReviewFactory(submission=submitted)
    event.review_phases.filter(is_active=True).update(can_review=True)

    with scope(event=event):
        assert rules.can_be_reviewed(None, submitted) is True
        assert rules.can_be_reviewed(None, review) is True
        assert rules.can_be_reviewed(None, accepted) is False

        event.review_phases.filter(is_active=True).update(can_review=False)
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_be_reviewed(None, submitted) is False

        event.review_phases.update(is_active=False, can_review=True)
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_be_reviewed(None, submitted) is False


def test_is_speaker():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker, SpeakerFactory(event=event, user=None))
    slot = TalkSlotFactory(submission=submission)

    with scope(event=event):
        assert rules.is_speaker(speaker.user, submission) is True
        assert rules.is_speaker(speaker.user, slot) is True
        assert rules.is_speaker(UserFactory(), submission) is False
        assert rules.is_speaker(AnonymousUser(), submission) is False
        assert rules.is_speaker(speaker.user, Submission()) is False


def test_is_review_author():
    review = ReviewFactory()

    assert rules.is_review_author(review.user, review) is True
    assert rules.is_review_author(UserFactory(), review) is False


def test_is_comment_author():
    comment = SubmissionCommentFactory()

    assert rules.is_comment_author(comment.user, comment) is True
    assert rules.is_comment_author(UserFactory(), comment) is False


@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["active", "inactive"],
)
def test_submission_comments_active(flag_value, expected):
    event = EventFactory(feature_flags={"use_submission_comments": flag_value})
    submission = SubmissionFactory(event=event)

    assert rules.submission_comments_active(None, submission) is expected


PHASE_PREDICATES = (
    "reviewer_can_create_tags",
    "reviewer_can_change_tags",
    "reviewer_can_change_submissions",
    "reviews_are_open",
    "can_view_all_reviews",
    "can_view_reviewer_names",
    "can_view_reviews",
)


@pytest.mark.parametrize(
    ("phase", "expected"),
    (
        (
            {
                "can_tag_submissions": "create_tags",
                "can_change_submission_state": True,
                "can_review": True,
                "can_see_other_reviews": "always",
                "can_see_reviewer_names": True,
            },
            {
                "reviewer_can_create_tags": True,
                "reviewer_can_change_tags": False,
                "reviewer_can_change_submissions": True,
                "reviews_are_open": True,
                "can_view_all_reviews": True,
                "can_view_reviewer_names": True,
                "can_view_reviews": True,
            },
        ),
        (
            {
                "can_tag_submissions": "use_tags",
                "can_change_submission_state": False,
                "can_review": False,
                "can_see_other_reviews": "never",
                "can_see_reviewer_names": False,
            },
            {
                "reviewer_can_create_tags": False,
                "reviewer_can_change_tags": True,
                "reviewer_can_change_submissions": False,
                "reviews_are_open": False,
                "can_view_all_reviews": False,
                "can_view_reviewer_names": False,
                "can_view_reviews": False,
            },
        ),
        ({"is_active": False}, dict.fromkeys(PHASE_PREDICATES, False)),
    ),
    ids=["permissive", "restrictive", "no_active_phase"],
)
def test_review_phase_predicates(phase, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(**phase)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert {
            name: getattr(rules, name)(None, submission) for name in PHASE_PREDICATES
        } == expected


def test_can_view_reviews_after_review_needs_own_review():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(
        can_see_other_reviews="after_review"
    )

    with scope(event=event):
        assert rules.can_view_reviews(user, submission) is False

        review = ReviewFactory(submission=submission, user=user)
        assert rules.can_view_reviews(user, submission) is True
        assert rules.can_view_reviews(user, review) is True


@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["tracks_enabled", "tracks_disabled"],
)
def test_use_tracks(flag_value, expected):
    event = EventFactory(feature_flags={"use_tracks": flag_value})
    submission = SubmissionFactory(event=event)

    assert rules.use_tracks(None, submission) is expected


def test_is_cfp_open():
    public = SubmissionFactory(
        event=EventFactory(is_public=True, cfp__opening=None, cfp__deadline=None)
    )
    private = SubmissionFactory(event=EventFactory(is_public=False))

    assert rules.is_cfp_open(None, public) is True
    assert rules.is_cfp_open(None, private) is False
    assert not rules.is_cfp_open(None, object())


def test_can_request_speakers():
    event = EventFactory(cfp__fields={"additional_speaker": {"visibility": "optional"}})
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    not_asked = SubmissionFactory(
        event=EventFactory(
            cfp__fields={"additional_speaker": {"visibility": "do_not_ask"}}
        ),
        state=SubmissionStates.SUBMITTED,
    )

    assert rules.can_request_speakers(None, submitted) is True
    assert rules.can_request_speakers(None, draft) is False
    assert rules.can_request_speakers(None, not_asked) is False


@pytest.mark.parametrize(
    ("version", "expected"), ((None, True), ("v1", False)), ids=["wip", "released"]
)
def test_is_wip(version, expected):
    schedule = ScheduleFactory(version=version)
    assert rules.is_wip(None, schedule) is expected


def test_is_wip_via_slot():
    slot = TalkSlotFactory()
    assert rules.is_wip(None, slot) is True


def test_is_feedback_ready_once_a_released_slot_has_started():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)

    with scope(event=event):
        assert rules.is_feedback_ready(None, submission) is False

        released = ScheduleFactory(event=event, version="v1")
        TalkSlotFactory(
            submission=submission,
            schedule=released,
            is_visible=True,
            start=tz_now() - dt.timedelta(hours=1),
        )
        submission = Submission.objects.select_related("event").get(pk=submission.pk)
        assert rules.is_feedback_ready(None, submission) is True


def test_is_break():
    event = EventFactory()
    room = RoomFactory(event=event)
    break_slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=room, start=None, end=None
    )
    talk_slot = TalkSlotFactory(schedule=event.wip_schedule, room=room)

    assert rules.is_break(None, break_slot) is True
    assert rules.is_break(None, talk_slot) is False


def test_orga_can_change_submissions():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    admin = UserFactory(is_administrator=True)
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    member = UserFactory()
    team.members.add(member)
    outsider = UserFactory()

    assert rules.orga_can_change_submissions(admin, submission) is True
    assert rules.orga_can_change_submissions(member, submission) is True
    assert rules.orga_can_change_submissions(outsider, submission) is False
    assert rules.orga_can_change_submissions(AnonymousUser(), submission) is False
    assert rules.orga_can_change_submissions(None, submission) is False
    assert rules.orga_can_change_submissions(admin, None) is False


def test_has_reviewer_access_follows_phase_visibility():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=other_track)
    reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    reviewer = UserFactory()
    admin_in_team = UserFactory(is_administrator=True)
    reviewer_team.members.add(reviewer, admin_in_team)
    track_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    track_team.limit_tracks.add(track)
    track_reviewer = UserFactory()
    track_team.members.add(track_reviewer)
    admin_alone = UserFactory(is_administrator=True)
    non_reviewer = UserFactory()
    submission.assigned_reviewers.add(non_reviewer)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        assert rules.has_reviewer_access(reviewer, submission) is True
        assert rules.has_reviewer_access(admin_in_team, submission) is True
        assert rules.has_reviewer_access(admin_alone, submission) is False
        assert rules.has_reviewer_access(track_reviewer, submission) is False
        assert rules.has_reviewer_access(non_reviewer, submission) is False

        event.review_phases.filter(is_active=True).update(
            proposal_visibility="assigned"
        )
        event.__dict__.pop("active_review_phase", None)
        assert rules.has_reviewer_access(reviewer, submission) is False
        assert rules.has_reviewer_access(non_reviewer, submission) is False
        submission.assigned_reviewers.add(reviewer)
        assert rules.has_reviewer_access(reviewer, submission) is True

        event.review_phases.update(is_active=False)
        event.__dict__.pop("active_review_phase", None)
        assert rules.has_reviewer_access(reviewer, submission) is False


def test_has_reviewer_access_blanket_team_with_extra_restricted_team():
    event = EventFactory()
    track_restricted = TrackFactory(event=event)
    track_other = TrackFactory(event=event)
    user = UserFactory()
    blanket = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    blanket.members.add(user)
    restricted = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    restricted.members.add(user)
    track_restricted.limit_teams.add(restricted)
    submission = SubmissionFactory(event=event, track=track_other)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is True


def test_orga_or_reviewer_can_change_submission_orga():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        assert rules.orga_or_reviewer_can_change_submission(user, submission) is True


@pytest.mark.parametrize(
    ("in_track", "can_change_state", "expected"),
    ((True, True, True), (False, True, False), (True, False, False)),
    ids=["in_track", "wrong_track", "phase_disallows_state_change"],
)
def test_orga_or_reviewer_can_change_submission_reviewer(
    in_track, can_change_state, expected
):
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    team.limit_tracks.add(track)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(
        event=event, track=track if in_track else other_track
    )
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="all", can_change_submission_state=can_change_state
    )

    with scope(event=event):
        assert (
            rules.orga_or_reviewer_can_change_submission(user, submission) is expected
        )


def test_orga_or_reviewer_can_change_submission_reviewer_unassigned():
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
    event.review_phases.filter(is_active=True).update(
        proposal_visibility="assigned", can_change_submission_state=True
    )

    with scope(event=event):
        assert rules.orga_or_reviewer_can_change_submission(user, submission) is False

    submission.assigned_reviewers.add(user)

    with scope(event=event):
        assert rules.orga_or_reviewer_can_change_submission(user, submission) is True


@pytest.mark.parametrize("user", (None, AnonymousUser()), ids=("none", "anonymous"))
def test_has_reviewer_access_invalid_user(user):
    assert rules.has_reviewer_access(user, None) is False


def test_has_reviewer_access_object_does_not_exist():

    class FakeSubmission:
        @property
        def event(self):
            raise ObjectDoesNotExist

    class FakeObj:
        submission = FakeSubmission()

    assert not rules.has_reviewer_access(UserFactory.build(), FakeObj())


def test_has_team_question_access():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    member = UserFactory()
    team.members.add(member)
    question = QuestionFactory(event=event)

    with scope(event=event):
        assert rules.has_team_question_access(member, question) is True
        assert rules.has_team_question_access(UserFactory(), question) is False


@pytest.mark.parametrize(
    ("is_featured", "state", "expected"),
    (
        (True, SubmissionStates.CONFIRMED, True),
        (True, SubmissionStates.SUBMITTED, True),
        (True, SubmissionStates.ACCEPTED, True),
        (False, SubmissionStates.CONFIRMED, False),
        (True, SubmissionStates.REJECTED, False),
        (True, SubmissionStates.CANCELED, False),
        (True, SubmissionStates.WITHDRAWN, False),
    ),
)
def test_is_featured_visible(is_featured, state, expected):
    event = EventFactory()
    with scope(event=event):
        submission = SubmissionFactory(
            event=event, is_featured=is_featured, state=state
        )

        assert rules.is_featured_visible(submission) is expected


def test_is_featured_visible_none():
    assert rules.is_featured_visible(None) is False
