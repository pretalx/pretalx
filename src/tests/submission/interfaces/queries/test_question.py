# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.submission.interfaces.queries.question import (
    answers_for_user,
    questions_for_user,
)
from pretalx.submission.models.question import QuestionTarget
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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
