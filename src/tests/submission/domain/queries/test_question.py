# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.question import (
    active_questions,
    answers_for_speaker,
    answers_for_user,
    count_missing_answers,
    filter_submissions_by_question,
    missing_questions_for_speaker,
    public_answers_for_speaker,
    public_answers_for_submission,
    questions_for_user,
)
from pretalx.submission.models import Submission
from pretalx.submission.models.question import QuestionTarget
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(("active", "should_include"), ((True, True), (False, False)))
def test_active_questions_filters_by_active_flag(active, should_include):
    event = EventFactory()
    question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, active=active
    )

    with scope(event=event):
        result = list(active_questions(event))

    assert (question in result) is should_include


def test_active_questions_filters_by_target_type():
    event = EventFactory()
    sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)

    with scope(event=event):
        result = list(active_questions(event, target=QuestionTarget.SUBMISSION))

    assert sub_q in result
    assert speaker_q not in result


def test_active_questions_no_target_excludes_reviewer_questions():
    """When target is None, all non-reviewer questions are included."""
    event = EventFactory()
    sub_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    speaker_q = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)

    with scope(event=event):
        result = list(active_questions(event, target=None))

    assert sub_q in result
    assert speaker_q in result
    assert reviewer_q not in result


def test_active_questions_filters_by_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    track_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    track_q.tracks.add(track)
    general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    other_q.tracks.add(other_track)

    with scope(event=event):
        result = list(active_questions(event, track=track))

    assert track_q in result
    assert general_q in result
    assert other_q not in result


def test_active_questions_filters_by_submission_type():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event)
    other_type = SubmissionTypeFactory(event=event)
    typed_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    typed_q.submission_types.add(sub_type)
    general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    other_q.submission_types.add(other_type)

    with scope(event=event):
        result = list(active_questions(event, submission_type=sub_type))

    assert typed_q in result
    assert general_q in result
    assert other_q not in result


def test_active_questions_skip_limited_drops_track_or_type_restricted():
    event = EventFactory()
    track = TrackFactory(event=event)
    general_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    limited_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    limited_q.tracks.add(track)

    with scope(event=event):
        result = list(active_questions(event, skip_limited=True))

    assert general_q in result
    assert limited_q not in result


def test_active_questions_for_reviewers_only_visible_to_reviewers():
    event = EventFactory()
    visible_q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, is_visible_to_reviewers=True
    )
    hidden_q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, is_visible_to_reviewers=False
    )

    with scope(event=event):
        result = list(active_questions(event, for_reviewers=True))

    assert visible_q in result
    assert hidden_q not in result


def test_questions_for_user_organiser_with_edit_perms():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event, active=False)

    with scope(event=event):
        result = questions_for_user(event, user)

    assert question in result


def test_questions_for_user_reviewer_sees_visible_and_reviewer_questions():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    team.members.add(user)

    event.review_phases.filter(is_active=True).update(can_see_speaker_names=True)

    visible_q = QuestionFactory(event=event, is_visible_to_reviewers=True, active=True)
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, active=True
    )
    hidden_q = QuestionFactory(event=event, is_visible_to_reviewers=False, active=True)

    with scope(event=event):
        result = questions_for_user(event, user)

    result_list = list(result)
    assert visible_q in result_list
    assert reviewer_q in result_list
    assert hidden_q not in result_list


def test_questions_for_user_anonymous_with_schedule():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    public_q = QuestionFactory(event=event, is_public=True)
    private_q = QuestionFactory(event=event, is_public=False)

    with scope(event=event):
        result = questions_for_user(event, AnonymousUser())

    result_list = list(result)
    assert public_q in result_list
    assert private_q not in result_list


def test_questions_for_user_anonymous_no_schedule():
    event = EventFactory(is_public=False)

    with scope(event=event):
        result = questions_for_user(event, AnonymousUser())

    assert result.count() == 0


def test_questions_for_user_filters_by_team():
    event = EventFactory()
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
        result = questions_for_user(event, user)

    result_list = list(result)
    assert question in result_list
    assert restricted_q not in result_list


def test_questions_for_user_reviewer_with_event_settings_treated_as_reviewer():
    """A user who is a reviewer AND has event-settings perms but cannot
    change submissions must be filtered like a reviewer, not an organiser —
    otherwise hidden-from-reviewer questions leak into review-context views."""
    event = EventFactory()
    reviewer_team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    settings_team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=False,
    )
    user = UserFactory()
    reviewer_team.members.add(user)
    settings_team.members.add(user)

    event.review_phases.filter(is_active=True).update(can_see_speaker_names=True)

    visible_q = QuestionFactory(event=event, is_visible_to_reviewers=True, active=True)
    hidden_q = QuestionFactory(event=event, is_visible_to_reviewers=False, active=True)

    with scope(event=event):
        result_list = list(questions_for_user(event, user))

    assert visible_q in result_list
    assert hidden_q not in result_list


def test_questions_for_user_update_question_perm():
    event = EventFactory()
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
        result = questions_for_user(event, user)

    assert question in result


@pytest.mark.parametrize("user", (AnonymousUser(), None), ids=["anonymous", "none"])
def test_answers_for_user_no_access_returns_none(user):
    event = EventFactory(is_public=False)
    question = QuestionFactory(event=event)
    AnswerFactory(question=question)

    with scope(event=event):
        assert answers_for_user(event, user or AnonymousUser()).count() == 0


def test_answers_for_user_authenticated_with_team_access():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    question = QuestionFactory(event=event)
    AnswerFactory(question=question)

    with scope(event=event):
        assert answers_for_user(event, user).count() == 1


def test_answers_for_user_excludes_team_restricted_questions():
    """Regression: previously filter_answers_by_team_access was a no-op,
    leaking answers to questions limited to other teams."""
    event = EventFactory()
    my_team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    other_team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    my_team.members.add(user)

    visible_q = QuestionFactory(event=event)
    restricted_q = QuestionFactory(event=event)
    restricted_q.limit_teams.add(other_team)

    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    visible_answer = AnswerFactory(question=visible_q, submission=submission)
    AnswerFactory(question=restricted_q, submission=submission)

    with scope(event=event):
        result = list(answers_for_user(event, user))

    assert visible_answer in result
    assert len(result) == 1


def test_filter_submissions_by_question_no_question_returns_unchanged():
    event = EventFactory()
    sub = SubmissionFactory(event=event)

    with scope(event=event):
        result = set(filter_submissions_by_question(event.submissions.all()))

    assert result == {sub}


def test_filter_submissions_by_question_by_answer_text():
    event = EventFactory()
    question = QuestionFactory(event=event)
    matching = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=matching, answer="yes")
    other = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=other, answer="no")

    with scope(event=event):
        result = set(
            filter_submissions_by_question(
                event.submissions.all(), question=question.pk, answer="yes"
            )
        )

    assert result == {matching}


def test_filter_submissions_by_question_by_option():
    event = EventFactory()
    question = QuestionFactory(event=event, variant="choices")
    option = AnswerOptionFactory(question=question)
    matching = SubmissionFactory(event=event)
    answer = AnswerFactory(question=question, submission=matching)
    answer.options.add(option)
    SubmissionFactory(event=event)

    with scope(event=event):
        result = set(
            filter_submissions_by_question(
                event.submissions.all(), question=question.pk, option=option.pk
            )
        )

    assert result == {matching}


def test_filter_submissions_by_question_returns_queryset_unchanged_without_filter():
    """A question without any of option/answer/unanswered acts as a no-op."""
    event = EventFactory()
    question = QuestionFactory(event=event)
    answered = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered)
    unanswered = SubmissionFactory(event=event)

    with scope(event=event):
        result = set(
            filter_submissions_by_question(
                event.submissions.all(), question=question.pk
            )
        )

    assert result == {answered, unanswered}


def test_filter_submissions_by_question_unanswered():
    event = EventFactory()
    question = QuestionFactory(event=event)
    answered = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=answered)
    unanswered = SubmissionFactory(event=event)

    with scope(event=event):
        result = set(
            filter_submissions_by_question(
                event.submissions.all(), question=question.pk, unanswered=True
            )
        )

    assert result == {unanswered}


def test_count_missing_answers_submission_all_missing():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    SubmissionFactory(event=event)
    SubmissionFactory(event=event)

    with scope(event=event):
        assert count_missing_answers(question) == 2


def test_count_missing_answers_submission_some_answered():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=event)
    SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=submission, speaker=None)

    with scope(event=event):
        assert count_missing_answers(question) == 1


def test_count_missing_answers_speaker():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        assert count_missing_answers(question) == 1


def test_count_missing_answers_speaker_answered():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    AnswerFactory(question=question, speaker=speaker, submission=None)

    with scope(event=event):
        assert count_missing_answers(question) == 0


def test_count_missing_answers_reviewer_returns_zero():
    question = QuestionFactory(target=QuestionTarget.REVIEWER)

    with scope(event=question.event):
        assert count_missing_answers(question) == 0


def test_count_missing_answers_with_filter_talks():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    sub1 = SubmissionFactory(event=event)
    SubmissionFactory(event=event)

    with scope(event=event):
        filtered = Submission.objects.filter(pk=sub1.pk)
        assert count_missing_answers(question, filter_talks=filtered) == 1


def test_count_missing_answers_with_filter_speakers():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        filtered = SpeakerProfile.objects.filter(pk=speaker.pk)
        assert count_missing_answers(question, filter_speakers=filtered) == 1


def test_answers_for_speaker_empty(event):
    speaker = SpeakerFactory(event=event)
    assert list(answers_for_speaker(speaker)) == []


def test_answers_for_speaker_includes_speaker_answers(event):
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    assert list(answers_for_speaker(speaker)) == [answer]


def test_answers_for_speaker_includes_submission_answers(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    answer = AnswerFactory(question=question, submission=submission, speaker=None)

    assert list(answers_for_speaker(speaker)) == [answer]


def test_answers_for_speaker_excludes_other_speakers(event):
    speaker = SpeakerFactory(event=event)
    other = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    AnswerFactory(question=question, speaker=other, submission=None)

    assert list(answers_for_speaker(speaker)) == []


def test_public_answers_for_submission_filters_public():
    submission = SubmissionFactory()
    event = submission.event
    q_public = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_private = QuestionFactory(
        event=event, is_public=False, target=QuestionTarget.SUBMISSION
    )
    a_public = AnswerFactory(question=q_public, submission=submission)
    AnswerFactory(question=q_private, submission=submission)

    with scope(event=event):
        result = list(public_answers_for_submission(submission))

    assert result == [a_public]


def test_public_answers_for_submission_filters_by_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    q_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    q_other_track = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    other_track = TrackFactory(event=event)
    q_track.tracks.add(track)
    q_other_track.tracks.add(other_track)
    a_track = AnswerFactory(question=q_track, submission=submission)
    AnswerFactory(question=q_other_track, submission=submission)

    with scope(event=event):
        result = list(public_answers_for_submission(submission))

    assert a_track in result
    assert all(a.question != q_other_track for a in result)


def test_public_answers_for_speaker_filters_public_speaker_target():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    public_q = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SPEAKER
    )
    private_q = QuestionFactory(
        event=event, is_public=False, target=QuestionTarget.SPEAKER
    )
    public_answer = AnswerFactory(question=public_q, speaker=speaker, submission=None)
    AnswerFactory(question=private_q, speaker=speaker, submission=None)

    with scope(event=event):
        result = list(public_answers_for_speaker(speaker))

    assert result == [public_answer]


def test_public_answers_for_speaker_excludes_submission_target_answers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    submission_q = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SUBMISSION
    )
    AnswerFactory(question=submission_q, speaker=speaker, submission=submission)

    with scope(event=event):
        result = list(public_answers_for_speaker(speaker))

    assert result == []


def test_public_answers_for_speaker_ordered_by_question_position():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    later = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SPEAKER, position=2
    )
    earlier = QuestionFactory(
        event=event, is_public=True, target=QuestionTarget.SPEAKER, position=1
    )
    later_answer = AnswerFactory(question=later, speaker=speaker, submission=None)
    earlier_answer = AnswerFactory(question=earlier, speaker=speaker, submission=None)

    with scope(event=event):
        result = list(public_answers_for_speaker(speaker))

    assert result == [earlier_answer, later_answer]


@pytest.mark.parametrize("target", ("submission", "speaker"))
def test_missing_questions_for_speaker_unanswered(target):
    event = EventFactory()
    question = QuestionFactory(event=event, target=target)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker, submissions=event.submissions.all(), questions=[question]
        )

    assert missing == [question]


def test_missing_questions_for_speaker_answered_excluded():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    AnswerFactory(question=question, speaker=speaker, answer="something")

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker, submissions=event.submissions.all(), questions=[question]
        )

    assert missing == []


def test_missing_questions_for_speaker_mixed():
    event = EventFactory()
    q_sub = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    q_speaker = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    AnswerFactory(question=q_speaker, speaker=speaker, answer="answered")

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker,
            submissions=event.submissions.all(),
            questions=[q_sub, q_speaker],
        )

    assert missing == [q_sub]


def test_missing_questions_for_speaker_ignores_reviewer_target():
    event = EventFactory()
    q_reviewer = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    q_sub = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker,
            submissions=event.submissions.all(),
            questions=[q_reviewer, q_sub],
        )

    assert missing == [q_sub]


def test_missing_questions_for_speaker_speaker_question_only_listed_once():
    """Speaker-target questions are independent of the number of submissions."""
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    sub_a = SubmissionFactory(event=event)
    sub_a.speakers.add(speaker)
    sub_b = SubmissionFactory(event=event)
    sub_b.speakers.add(speaker)

    with scope(event=event):
        missing = missing_questions_for_speaker(
            speaker=speaker, submissions=event.submissions.all(), questions=[question]
        )

    assert missing == [question]
