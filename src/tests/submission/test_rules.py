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
    ("state", "expected"),
    (
        ("submitted", True),
        ("accepted", True),
        ("rejected", False),
        ("confirmed", False),
        ("canceled", False),
        ("withdrawn", False),
        ("draft", False),
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
def test_can_be_withdrawn(state, expected):
    submission = Submission(state=state)
    assert rules.can_be_withdrawn(None, submission) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("submitted", False),
        ("accepted", True),
        ("rejected", False),
        ("confirmed", False),
        ("canceled", False),
        ("withdrawn", False),
        ("draft", False),
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
def test_can_be_confirmed(state, expected):
    submission = Submission(state=state)
    assert rules.can_be_confirmed(None, submission) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("submitted", True),
        ("accepted", True),
        ("rejected", True),
        ("confirmed", True),
        ("canceled", True),
        ("withdrawn", True),
        ("draft", False),
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
def test_can_be_removed(state, expected):
    submission = Submission(state=state)
    assert rules.can_be_removed(None, submission) is expected


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


def test_can_be_reviewed_submitted_with_active_phase():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    event.review_phases.filter(is_active=True).update(can_review=True)

    with scope(event=event):
        assert rules.can_be_reviewed(None, submission) is True


def test_can_be_reviewed_not_submitted():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    event.review_phases.filter(is_active=True).update(can_review=True)

    with scope(event=event):
        assert rules.can_be_reviewed(None, submission) is False


def test_can_be_reviewed_no_active_phase():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    event.review_phases.update(is_active=False)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_be_reviewed(None, submission) is False


def test_can_be_reviewed_phase_review_disabled():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    event.review_phases.filter(is_active=True).update(can_review=False)

    with scope(event=event):
        assert rules.can_be_reviewed(None, submission) is False


def test_can_be_reviewed_via_review_object():
    """can_be_reviewed follows .submission when given a Review object."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    review = ReviewFactory(submission=submission)
    event.review_phases.filter(is_active=True).update(can_review=True)

    with scope(event=event):
        assert rules.can_be_reviewed(None, review) is True


def test_is_speaker_true():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        assert rules.is_speaker(speaker.user, submission) is True


def test_is_speaker_false():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        assert rules.is_speaker(user, submission) is False


def test_is_speaker_via_slot():
    """is_speaker follows .submission when given a slot-like object."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission)

    with scope(event=event):
        assert rules.is_speaker(speaker.user, slot) is True


def test_is_speaker_no_pk():
    submission = Submission()
    assert not rules.is_speaker(None, submission)


@pytest.mark.parametrize(
    ("own_review", "expected"),
    ((True, True), (False, False)),
    ids=["author", "not_author"],
)
def test_is_review_author(own_review, expected):
    review = ReviewFactory()
    user = review.user if own_review else UserFactory()
    assert rules.is_review_author(user, review) is expected


@pytest.mark.parametrize(
    ("own_comment", "expected"),
    ((True, True), (False, False)),
    ids=["author", "not_author"],
)
def test_is_comment_author(own_comment, expected):
    comment = SubmissionCommentFactory()
    user = comment.user if own_comment else UserFactory()
    assert rules.is_comment_author(user, comment) is expected


@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["active", "inactive"],
)
def test_submission_comments_active(flag_value, expected):
    event = EventFactory(feature_flags={"use_submission_comments": flag_value})
    submission = SubmissionFactory(event=event)

    assert rules.submission_comments_active(None, submission) is expected


@pytest.mark.parametrize(
    ("tag_setting", "expected"),
    (("create_tags", True), ("use_tags", False)),
    ids=["create_tags", "use_tags"],
)
def test_reviewer_can_create_tags(tag_setting, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_tag_submissions=tag_setting)
    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_create_tags(None, submission) is expected


def test_reviewer_can_create_tags_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviewer_can_create_tags(None, submission) is False


@pytest.mark.parametrize(
    ("tag_setting", "expected"),
    (("use_tags", True), ("create_tags", False)),
    ids=["use_tags", "create_tags"],
)
def test_reviewer_can_change_tags(tag_setting, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_tag_submissions=tag_setting)
    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_change_tags(None, submission) is expected


@pytest.mark.parametrize(
    ("can_change", "expected"),
    ((True, True), (False, False)),
    ids=["can_change", "cannot_change"],
)
def test_reviewer_can_change_submissions(can_change, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(
        can_change_submission_state=can_change
    )
    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_change_submissions(None, submission) is expected


def test_reviewer_can_change_submissions_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviewer_can_change_submissions(None, submission) is False


@pytest.mark.parametrize(
    ("can_review", "expected"), ((True, True), (False, False)), ids=["open", "closed"]
)
def test_reviews_are_open(can_review, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_review=can_review)
    submission = SubmissionFactory(event=event)
    assert rules.reviews_are_open(None, submission) is expected


def test_reviews_are_open_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviews_are_open(None, submission) is False


@pytest.mark.parametrize(
    ("visibility", "expected"),
    (("always", True), ("never", False)),
    ids=["always", "never"],
)
def test_can_view_all_reviews(visibility, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_see_other_reviews=visibility)
    submission = SubmissionFactory(event=event)
    assert rules.can_view_all_reviews(None, submission) is expected


@pytest.mark.parametrize(
    ("can_see", "expected"), ((True, True), (False, False)), ids=["visible", "hidden"]
)
def test_can_view_reviewer_names(can_see, expected):
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_see_reviewer_names=can_see)
    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviewer_names(None, submission) is expected


def test_can_view_reviewer_names_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_view_reviewer_names(None, submission) is False


def test_can_view_reviews_always():
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_see_other_reviews="always")
    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviews(None, submission) is True


def test_can_view_reviews_after_review_with_own_review():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=user)
    event.review_phases.filter(is_active=True).update(
        can_see_other_reviews="after_review"
    )

    with scope(event=event):
        assert rules.can_view_reviews(user, submission) is True


def test_can_view_reviews_after_review_without_own_review():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(
        can_see_other_reviews="after_review"
    )

    with scope(event=event):
        assert rules.can_view_reviews(user, submission) is False


def test_can_view_reviews_never():
    event = EventFactory()
    event.review_phases.filter(is_active=True).update(can_see_other_reviews="never")
    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviews(None, submission) is False


def test_can_view_reviews_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_view_reviews(None, submission) is False


def test_can_view_reviews_after_review_via_review_object():
    """can_view_reviews resolves Review -> submission correctly."""
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, user=user)
    event.review_phases.filter(is_active=True).update(
        can_see_other_reviews="after_review"
    )

    with scope(event=event):
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


def test_is_cfp_open_true():
    event = EventFactory(is_public=True, cfp__opening=None, cfp__deadline=None)
    submission = SubmissionFactory(event=event)
    assert rules.is_cfp_open(None, submission) is True


def test_is_cfp_open_false_not_public():
    event = EventFactory(is_public=False)
    submission = SubmissionFactory(event=event)

    assert rules.is_cfp_open(None, submission) is False


def test_is_cfp_open_no_event():
    assert not rules.is_cfp_open(None, object())


def test_can_request_speakers_true():
    event = EventFactory(cfp__fields={"additional_speaker": {"visibility": "optional"}})
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert rules.can_request_speakers(None, submission) is True


def test_can_request_speakers_false_draft():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    assert rules.can_request_speakers(None, submission) is False


def test_can_request_speakers_false_not_requested():
    event = EventFactory(
        cfp__fields={"additional_speaker": {"visibility": "do_not_ask"}}
    )
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert rules.can_request_speakers(None, submission) is False


@pytest.mark.parametrize(
    ("version", "expected"), ((None, True), ("v1", False)), ids=["wip", "released"]
)
def test_is_wip(version, expected):
    schedule = ScheduleFactory(version=version)
    assert rules.is_wip(None, schedule) is expected


def test_is_wip_via_slot():
    slot = TalkSlotFactory()
    assert rules.is_wip(None, slot) is True


def test_is_feedback_ready_true():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    released = ScheduleFactory(event=event, version="v1")
    TalkSlotFactory(
        submission=submission,
        schedule=released,
        is_visible=True,
        start=tz_now() - dt.timedelta(hours=1),
    )

    with scope(event=event):
        assert rules.is_feedback_ready(None, submission) is True


def test_is_feedback_ready_false_no_slot():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        assert rules.is_feedback_ready(None, submission) is False


def test_is_break_true():
    event = EventFactory()
    room = RoomFactory(event=event)
    slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=room, start=None, end=None
    )
    assert rules.is_break(None, slot) is True


def test_is_break_false():
    slot = TalkSlotFactory()
    assert rules.is_break(None, slot) is False


def test_orga_can_change_submissions_administrator():
    event = EventFactory()
    user = UserFactory(is_administrator=True)
    submission = SubmissionFactory(event=event)
    assert rules.orga_can_change_submissions(user, submission) is True


def test_orga_can_change_submissions_with_permission():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    assert rules.orga_can_change_submissions(user, submission) is True


def test_orga_can_change_submissions_without_permission():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)

    assert rules.orga_can_change_submissions(user, submission) is False


def test_orga_can_change_submissions_anonymous():
    assert rules.orga_can_change_submissions(AnonymousUser(), Submission()) is False


def test_orga_can_change_submissions_no_obj():
    user = UserFactory.build()
    assert rules.orga_can_change_submissions(user, None) is False


def test_orga_can_change_submissions_no_user():
    assert rules.orga_can_change_submissions(None, Submission()) is False


def test_has_reviewer_access_all_proposals():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is True


@pytest.mark.parametrize(
    ("with_team", "expected"),
    ((False, False), (True, True)),
    ids=("admin_without_team_denied", "admin_with_team_allowed"),
)
def test_has_reviewer_access_administrator(with_team, expected):
    event = EventFactory()
    user = UserFactory(is_administrator=True)
    if with_team:
        team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
        team.members.add(user)
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is expected


def test_has_reviewer_access_all_proposals_wrong_track():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.limit_tracks.add(track1)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event, track=track2)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is False


def test_has_reviewer_access_assigned_only():
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)
    event.review_phases.filter(is_active=True).update(proposal_visibility="assigned")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is False

    submission.assigned_reviewers.add(user)

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is True


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


def test_has_reviewer_access_non_reviewer_assigned():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    submission.assigned_reviewers.add(user)
    event.review_phases.filter(is_active=True).update(proposal_visibility="assigned")

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is False


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


def test_has_reviewer_access_no_phase():
    event = EventFactory()
    event.review_phases.update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.has_reviewer_access(None, submission) is False


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


def test_has_team_question_access_true():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event)

    with scope(event=event):
        assert rules.has_team_question_access(user, question) is True


def test_has_team_question_access_false():
    event = EventFactory()
    question = QuestionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        assert rules.has_team_question_access(user, question) is False


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
