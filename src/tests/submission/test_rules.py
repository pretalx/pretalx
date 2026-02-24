import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now as tz_now
from django_scopes import scope, scopes_disabled

from pretalx.schedule.models import Schedule
from pretalx.submission import rules
from pretalx.submission.models import Question, Submission, SubmissionStates
from pretalx.submission.models.question import Answer, QuestionTarget
from tests.factories import (
    AnswerFactory,
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

pytestmark = pytest.mark.unit


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


@pytest.mark.django_db
def test_can_be_reviewed_submitted_with_active_phase(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_review = True
        phase.save()

        assert rules.can_be_reviewed(None, submission) is True


@pytest.mark.django_db
def test_can_be_reviewed_not_submitted(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_review = True
        phase.save()

        assert rules.can_be_reviewed(None, submission) is False


@pytest.mark.django_db
def test_can_be_reviewed_no_active_phase(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scopes_disabled():
        event.review_phases.all().update(is_active=False)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_be_reviewed(None, submission) is False


@pytest.mark.django_db
def test_can_be_reviewed_phase_review_disabled(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_review = False
        phase.save()

        assert rules.can_be_reviewed(None, submission) is False


@pytest.mark.django_db
def test_can_be_reviewed_via_review_object(event):
    """can_be_reviewed follows .submission when given a Review object."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    review = ReviewFactory(submission=submission)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_review = True
        phase.save()

        assert rules.can_be_reviewed(None, review) is True


@pytest.mark.django_db
def test_is_speaker_true(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    with scope(event=event):
        assert rules.is_speaker(speaker.user, submission) is True


@pytest.mark.django_db
def test_is_speaker_false(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        assert rules.is_speaker(user, submission) is False


@pytest.mark.django_db
def test_is_speaker_via_slot(event):
    """is_speaker follows .submission when given a slot-like object."""
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission)

    with scope(event=event):
        assert rules.is_speaker(speaker.user, slot) is True


def test_is_speaker_no_pk():
    submission = Submission()
    assert not rules.is_speaker(None, submission)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("own_review", "expected"),
    ((True, True), (False, False)),
    ids=["author", "not_author"],
)
def test_is_review_author(own_review, expected):
    review = ReviewFactory()
    user = review.user if own_review else UserFactory()
    assert rules.is_review_author(user, review) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("own_comment", "expected"),
    ((True, True), (False, False)),
    ids=["author", "not_author"],
)
def test_is_comment_author(own_comment, expected):
    comment = SubmissionCommentFactory()
    user = comment.user if own_comment else UserFactory()
    assert rules.is_comment_author(user, comment) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["active", "inactive"],
)
def test_submission_comments_active(flag_value, expected, event):
    event.feature_flags["use_submission_comments"] = flag_value
    event.save()
    submission = SubmissionFactory(event=event)

    assert rules.submission_comments_active(None, submission) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tag_setting", "expected"),
    (("create_tags", True), ("use_tags", False)),
    ids=["create_tags", "use_tags"],
)
def test_reviewer_can_create_tags(tag_setting, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_tag_submissions = tag_setting
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_create_tags(None, submission) is expected


@pytest.mark.django_db
def test_reviewer_can_create_tags_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviewer_can_create_tags(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tag_setting", "expected"),
    (("use_tags", True), ("create_tags", False)),
    ids=["use_tags", "create_tags"],
)
def test_reviewer_can_change_tags(tag_setting, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_tag_submissions = tag_setting
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_change_tags(None, submission) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("can_change", "expected"),
    ((True, True), (False, False)),
    ids=["can_change", "cannot_change"],
)
def test_reviewer_can_change_submissions(can_change, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_change_submission_state = can_change
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.reviewer_can_change_submissions(None, submission) is expected


@pytest.mark.django_db
def test_reviewer_can_change_submissions_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviewer_can_change_submissions(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("can_review", "expected"), ((True, True), (False, False)), ids=["open", "closed"]
)
def test_reviews_are_open(can_review, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_review = can_review
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.reviews_are_open(None, submission) is expected


@pytest.mark.django_db
def test_reviews_are_open_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.reviews_are_open(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("visibility", "expected"),
    (("always", True), ("never", False)),
    ids=["always", "never"],
)
def test_can_view_all_reviews(visibility, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = visibility
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.can_view_all_reviews(None, submission) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("can_see", "expected"), ((True, True), (False, False)), ids=["visible", "hidden"]
)
def test_can_view_reviewer_names(can_see, expected, event):
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_reviewer_names = can_see
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviewer_names(None, submission) is expected


@pytest.mark.django_db
def test_can_view_reviewer_names_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_view_reviewer_names(None, submission) is False


@pytest.mark.django_db
def test_can_view_reviews_always(event):
    """When phase says 'always', any user can view reviews."""
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = "always"
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviews(None, submission) is True


@pytest.mark.django_db
def test_can_view_reviews_after_review_with_own_review(event):
    """When phase says 'after_review', user who has reviewed can view."""
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=user)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = "after_review"
        phase.save()

        assert rules.can_view_reviews(user, submission) is True


@pytest.mark.django_db
def test_can_view_reviews_after_review_without_own_review(event):
    """When phase says 'after_review', user who hasn't reviewed cannot view."""
    user = UserFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = "after_review"
        phase.save()

        assert rules.can_view_reviews(user, submission) is False


@pytest.mark.django_db
def test_can_view_reviews_never(event):
    """When phase says 'never', nobody can view."""
    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = "never"
        phase.save()

    submission = SubmissionFactory(event=event)
    assert rules.can_view_reviews(None, submission) is False


@pytest.mark.django_db
def test_can_view_reviews_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.can_view_reviews(None, submission) is False


@pytest.mark.django_db
def test_can_view_reviews_after_review_via_review_object(event):
    """can_view_reviews resolves Review -> submission correctly."""
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, user=user)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_other_reviews = "after_review"
        phase.save()

        assert rules.can_view_reviews(user, review) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["tracks_enabled", "tracks_disabled"],
)
def test_use_tracks(flag_value, expected, event):
    event.feature_flags["use_tracks"] = flag_value
    event.save()
    submission = SubmissionFactory(event=event)

    assert rules.use_tracks(None, submission) is expected


@pytest.mark.django_db
def test_is_cfp_open_true(event):
    event.is_public = True
    event.save()

    with scope(event=event):
        cfp = event.cfp
        cfp.opening = None
        cfp.deadline = None
        cfp.save()

    submission = SubmissionFactory(event=event)
    assert rules.is_cfp_open(None, submission) is True


@pytest.mark.django_db
def test_is_cfp_open_false_not_public(event):
    event.is_public = False
    event.save()
    submission = SubmissionFactory(event=event)

    assert rules.is_cfp_open(None, submission) is False


def test_is_cfp_open_no_event():
    assert not rules.is_cfp_open(None, object())


@pytest.mark.django_db
def test_can_request_speakers_true(event):
    with scope(event=event):
        cfp = event.cfp
        fields = cfp.fields
        fields["additional_speaker"]["visibility"] = "optional"
        cfp.fields = fields
        cfp.save()

    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert rules.can_request_speakers(None, submission) is True


@pytest.mark.django_db
def test_can_request_speakers_false_draft(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    assert rules.can_request_speakers(None, submission) is False


@pytest.mark.django_db
def test_can_request_speakers_false_not_requested(event):
    with scope(event=event):
        cfp = event.cfp
        fields = cfp.fields
        fields["additional_speaker"]["visibility"] = "do_not_ask"
        cfp.fields = fields
        cfp.save()

    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    assert rules.can_request_speakers(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("version", "expected"), ((None, True), ("v1", False)), ids=["wip", "released"]
)
def test_is_wip(version, expected):
    schedule = ScheduleFactory(version=version)
    assert rules.is_wip(None, schedule) is expected


@pytest.mark.django_db
def test_is_wip_via_slot():
    """is_wip follows .schedule on slot-like objects."""
    slot = TalkSlotFactory()
    with scopes_disabled():
        slot.schedule.version = None
        slot.schedule.save()
    assert rules.is_wip(None, slot) is True


@pytest.mark.django_db
def test_is_feedback_ready_true(event):
    """Submission with a past slot start accepts feedback."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        released = ScheduleFactory(event=event, version="v1")
        released.published = tz_now()
        released.save()
        TalkSlotFactory(
            submission=submission,
            schedule=released,
            is_visible=True,
            start=tz_now() - dt.timedelta(hours=1),
        )

    with scope(event=event):
        assert rules.is_feedback_ready(None, submission) is True


@pytest.mark.django_db
def test_is_feedback_ready_false_no_slot(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        assert rules.is_feedback_ready(None, submission) is False


@pytest.mark.django_db
def test_is_break_true(event):
    room = RoomFactory(event=event)
    with scopes_disabled():
        slot = TalkSlotFactory(
            submission=None,
            schedule=event.wip_schedule,
            room=room,
            start=None,
            end=None,
        )
    assert rules.is_break(None, slot) is True


@pytest.mark.django_db
def test_is_break_false():
    slot = TalkSlotFactory()
    assert rules.is_break(None, slot) is False


@pytest.mark.django_db
def test_orga_can_change_submissions_administrator(event):
    user = UserFactory(is_administrator=True)
    submission = SubmissionFactory(event=event)
    assert rules.orga_can_change_submissions(user, submission) is True


@pytest.mark.django_db
def test_orga_can_change_submissions_with_permission(event):
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    assert rules.orga_can_change_submissions(user, submission) is True


@pytest.mark.django_db
def test_orga_can_change_submissions_without_permission(event):
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


@pytest.mark.django_db
def test_has_reviewer_access_all_proposals(event):
    """When phase.proposal_visibility is 'all' and no track restrictions, reviewer has access."""
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        assert rules.has_reviewer_access(user, submission) is True


@pytest.mark.django_db
def test_has_reviewer_access_all_proposals_wrong_track(event):
    """When reviewer is restricted to a track and submission is on a different track."""
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.limit_tracks.add(track1)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event, track=track2)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        assert rules.has_reviewer_access(user, submission) is False


@pytest.mark.django_db
def test_has_reviewer_access_assigned_only(event):
    """When phase.proposal_visibility is 'assigned', only assigned reviewers have access."""
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "assigned"
        phase.save()

        assert rules.has_reviewer_access(user, submission) is False

    with scopes_disabled():
        submission.assigned_reviewers.add(user)

    with scope(event=event):
        assert rules.has_reviewer_access(user, submission) is True


@pytest.mark.django_db
def test_has_reviewer_access_no_phase(event):
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        assert rules.has_reviewer_access(None, submission) is False


def test_has_reviewer_access_none():
    assert rules.has_reviewer_access(None, None) is False


def test_has_reviewer_access_object_does_not_exist():
    """has_reviewer_access returns False when obj.event raises ObjectDoesNotExist."""

    class FakeSubmission:
        @property
        def event(self):
            raise ObjectDoesNotExist

    class FakeObj:
        submission = FakeSubmission()

    assert not rules.has_reviewer_access(None, FakeObj())


@pytest.mark.django_db
def test_are_featured_submissions_visible_never(event):
    event.is_public = True
    event.feature_flags["show_featured"] = "never"
    event.save()

    assert rules.are_featured_submissions_visible(None, event) is False


@pytest.mark.django_db
def test_are_featured_submissions_visible_not_public(event):
    event.is_public = False
    event.save()

    assert rules.are_featured_submissions_visible(None, event) is False


@pytest.mark.django_db
def test_are_featured_submissions_visible_always(event):
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.save()

    assert rules.are_featured_submissions_visible(None, event) is True


@pytest.mark.django_db
def test_are_featured_submissions_visible_pre_schedule(event):
    """Default 'pre_schedule' shows featured when there's no current schedule."""
    event.is_public = True
    event.feature_flags["show_featured"] = "pre_schedule"
    event.save()

    with scope(event=event):
        assert rules.are_featured_submissions_visible(None, event) is True


@pytest.mark.django_db
@pytest.mark.parametrize("user", (AnonymousUser(), None), ids=["anonymous", "none"])
def test_filter_answers_by_team_access_no_user(user):
    event = EventFactory()
    with scopes_disabled():
        qs = Answer.objects.filter(question__event=event)
    result = rules.filter_answers_by_team_access(qs, user)
    assert result.count() == 0


@pytest.mark.django_db
def test_filter_answers_by_team_access_authenticated_user():
    event = EventFactory()
    question = QuestionFactory(event=event)
    AnswerFactory(question=question)
    user = UserFactory()

    with scopes_disabled():
        qs = Answer.objects.filter(question__event=event)
        result = rules.filter_answers_by_team_access(qs, user)
    assert result.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("user", (AnonymousUser(), None), ids=["anonymous", "none"])
def test_filter_questions_by_team_access_no_user(user):
    event = EventFactory()
    with scopes_disabled():
        qs = Question.objects.filter(event=event)
    result = rules.filter_questions_by_team_access(qs, user)
    assert result.count() == 0


@pytest.mark.django_db
def test_filter_questions_by_team_access_no_limit_teams():
    """Questions with no limit_teams are visible to all authenticated users."""
    event = EventFactory()
    question = QuestionFactory(event=event)
    user = UserFactory()

    with scopes_disabled():
        qs = Question.objects.filter(event=event, pk=question.pk)
        result = rules.filter_questions_by_team_access(qs, user)
    assert list(result) == [question]


@pytest.mark.django_db
def test_filter_questions_by_team_access_with_limit_teams():
    """Questions with limit_teams are only visible to members of those teams."""
    event = EventFactory()
    question = QuestionFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True)
    question.limit_teams.add(team)
    user_in_team = UserFactory()
    team.members.add(user_in_team)
    user_outside = UserFactory()

    with scopes_disabled():
        qs = Question.objects.filter(event=event, pk=question.pk)
        assert list(rules.filter_questions_by_team_access(qs, user_in_team)) == [
            question
        ]
        assert list(rules.filter_questions_by_team_access(qs, user_outside)) == []


@pytest.mark.django_db
def test_questions_for_user_organiser_with_edit_perms(event):
    """Organisers with update_question permission see all questions including inactive."""
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event, active=False)

    with scope(event=event):
        result = rules.questions_for_user(event, user)

    with scopes_disabled():
        assert question in result


@pytest.mark.django_db
def test_questions_for_user_reviewer_sees_visible_and_reviewer_questions(event):
    """Reviewer-only user sees questions marked visible_to_reviewers and reviewer target questions."""
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_speaker_names = True
        phase.save()

    visible_q = QuestionFactory(event=event, is_visible_to_reviewers=True, active=True)
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    hidden_q = QuestionFactory(event=event, is_visible_to_reviewers=False, active=True)

    with scope(event=event):
        result = rules.questions_for_user(event, user)

    with scopes_disabled():
        result_list = list(result)
    assert visible_q in result_list
    assert reviewer_q in result_list
    assert hidden_q not in result_list


@pytest.mark.django_db
def test_questions_for_user_anonymous_with_schedule(event):
    """Anonymous users with schedule access see only public questions."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()

    with scopes_disabled():
        Schedule.objects.create(event=event, version="v1")

    public_q = QuestionFactory(event=event, is_public=True)
    private_q = QuestionFactory(event=event, is_public=False)

    with scope(event=event):
        result = rules.questions_for_user(event, AnonymousUser())

    with scopes_disabled():
        result_list = list(result)
    assert public_q in result_list
    assert private_q not in result_list


@pytest.mark.django_db
def test_questions_for_user_anonymous_no_schedule(event):
    """Anonymous users without schedule access see nothing."""
    event.is_public = False
    event.save()

    with scope(event=event):
        result = rules.questions_for_user(event, AnonymousUser())

    assert result.count() == 0


@pytest.mark.django_db
def test_questions_for_user_for_answers_filters_by_team(event):
    """When for_answers=True, results are filtered through filter_questions_by_team_access."""
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event)
    restricted_q = QuestionFactory(event=event)
    other_team = TeamFactory(organiser=event.organiser, all_events=True)
    restricted_q.limit_teams.add(other_team)

    with scope(event=event):
        result = rules.questions_for_user(event, user, for_answers=True)

    with scopes_disabled():
        result_list = list(result)
    assert question in result_list
    assert restricted_q not in result_list


@pytest.mark.django_db
def test_has_team_question_access_true(event):
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event)

    with scope(event=event):
        assert rules.has_team_question_access(user, question) is True


@pytest.mark.django_db
def test_has_team_question_access_false(event):
    question = QuestionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        assert rules.has_team_question_access(user, question) is False


@pytest.mark.django_db
def test_annotate_assigned(event):
    user = UserFactory()
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)
    with scopes_disabled():
        s1.assigned_reviewers.add(user)

    with scope(event=event):
        qs = rules.annotate_assigned(event.submissions.all(), event, user)
        assigned = {s.pk: s.is_assigned for s in qs}

    assert assigned[s1.pk] is True
    assert assigned[s2.pk] is False


@pytest.mark.django_db
def test_limit_for_reviewers_excludes_own_submissions(event):
    """Reviewers cannot see their own submissions."""
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    own_sub = SubmissionFactory(event=event)
    other_sub = SubmissionFactory(event=event)
    with scopes_disabled():
        own_sub.speakers.add(speaker)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        qs = rules.limit_for_reviewers(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert own_sub.pk not in result_pks
    assert other_sub.pk in result_pks


@pytest.mark.django_db
def test_limit_for_reviewers_assigned_visibility(event):
    """When proposal_visibility is 'assigned', only assigned submissions are returned."""
    user = UserFactory()
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)
    with scopes_disabled():
        s1.assigned_reviewers.add(user)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "assigned"
        phase.save()

        qs = rules.limit_for_reviewers(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk not in result_pks


@pytest.mark.django_db
def test_limit_for_reviewers_track_restriction(event):
    """When reviewer has track restrictions, only submissions on those tracks are returned."""
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.limit_tracks.add(track1)
    user = UserFactory()
    team.members.add(user)
    s1 = SubmissionFactory(event=event, track=track1)
    s2 = SubmissionFactory(event=event, track=track2)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        qs = rules.limit_for_reviewers(event.submissions.all(), event, user)
        result_pks = set(qs.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk not in result_pks


@pytest.mark.django_db
def test_limit_for_reviewers_no_phase_returns_empty(event):
    """When there is no active review phase, returns empty queryset."""
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
    user = UserFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        event.__dict__.pop("active_review_phase", None)
        qs = rules.limit_for_reviewers(event.submissions.all(), event, user)
    assert qs.count() == 0


@pytest.mark.django_db
def test_submissions_for_user_organiser(event):
    """Organiser sees all submissions."""
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)

    with scope(event=event):
        result = rules.submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk in result_pks


@pytest.mark.django_db
def test_submissions_for_user_reviewer(event):
    """Reviewer-only user gets submissions via limit_for_reviewers."""
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        result = rules.submissions_for_user(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert submission.pk in result_pks


@pytest.mark.django_db
def test_submissions_for_user_anonymous_with_schedule(event):
    """Anonymous users with schedule access see scheduled submissions."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    released = ScheduleFactory(event=event, version="v1")
    with scopes_disabled():
        released.published = tz_now()
        released.save()
    TalkSlotFactory(submission=submission, schedule=released, is_visible=True)

    with scope(event=event):
        result = rules.submissions_for_user(event, AnonymousUser())

    assert submission.pk in set(result.values_list("pk", flat=True))


@pytest.mark.django_db
def test_submissions_for_user_anonymous_no_schedule(event):
    """Anonymous users without schedule access see nothing."""
    event.is_public = False
    event.save()
    SubmissionFactory(event=event)

    with scope(event=event):
        result = rules.submissions_for_user(event, AnonymousUser())

    assert result.count() == 0


@pytest.mark.django_db
def test_speakers_for_user(event):
    """speakers_for_user returns profiles of speakers in visible submissions."""
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    with scope(event=event):
        result = rules.speakers_for_user(event, user)

    assert speaker in result


@pytest.mark.django_db
def test_get_reviewable_submissions(event):
    """Returns submitted submissions ordered by review count, excluding own."""
    user = UserFactory()
    s1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.can_review = True
        phase.save()

        result = rules.get_reviewable_submissions(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk in result_pks


@pytest.mark.django_db
def test_get_missing_reviews(event):
    """Returns submissions the user hasn't reviewed yet."""
    user = UserFactory()
    s1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=s1, user=user)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.can_review = True
        phase.save()

        result = rules.get_missing_reviews(event, user)
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk not in result_pks
    assert s2.pk in result_pks


@pytest.mark.django_db
def test_get_missing_reviews_with_ignore(event):
    """Submissions in the ignore list are excluded."""
    user = UserFactory()
    s1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    s2 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.can_review = True
        phase.save()

        result = rules.get_missing_reviews(event, user, ignore=[s1.pk])
        result_pks = set(result.values_list("pk", flat=True))

    assert s1.pk not in result_pks
    assert s2.pk in result_pks


@pytest.mark.django_db
def test_questions_for_user_update_question_perm(event):
    """Users with can_change_event_settings see all questions via update_question path."""
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event, active=False)

    with scope(event=event):
        result = rules.questions_for_user(event, user)

    with scopes_disabled():
        assert question in result


@pytest.mark.django_db
def test_limit_for_reviewers_explicit_reviewer_tracks(event):
    """Passing reviewer_tracks explicitly skips the get_reviewer_tracks call."""
    track = TrackFactory(event=event)
    user = UserFactory()
    s1 = SubmissionFactory(event=event, track=track)
    s2 = SubmissionFactory(event=event)

    with scope(event=event):
        phase = event.active_review_phase
        phase.proposal_visibility = "all"
        phase.save()

        qs = rules.limit_for_reviewers(
            event.submissions.all(), event, user, reviewer_tracks=[track]
        )
        result_pks = set(qs.values_list("pk", flat=True))

    assert s1.pk in result_pks
    assert s2.pk not in result_pks


@pytest.mark.django_db
def test_submissions_for_user_authenticated_no_permissions(event):
    """Authenticated user without organiser or reviewer role falls through to schedule check."""
    event.is_public = False
    event.save()
    user = UserFactory()
    SubmissionFactory(event=event)

    with scope(event=event):
        result = rules.submissions_for_user(event, user)

    assert result.count() == 0
