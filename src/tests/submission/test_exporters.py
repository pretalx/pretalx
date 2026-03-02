# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from pretalx.submission.exporters import SpeakerQuestionData, SubmissionQuestionData
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_question_data_get_csv_data_returns_speaker_answers():
    """Any authenticated user can export all speaker answers — access control
    in filter_answers_by_team_access is a no-op for non-anonymous users."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(
        event=event, target="speaker", question="Favourite colour?"
    )
    AnswerFactory(question=question, speaker=speaker, submission=None, answer="Blue")

    request = _authenticated_request()

    field_names, data = SpeakerQuestionData(event).get_csv_data(request)

    assert field_names == ["code", "name", "email", "question", "answer"]
    assert len(data) == 1
    assert data[0]["code"] == speaker.code
    assert data[0]["name"] == speaker.get_display_name()
    assert data[0]["email"] == speaker.user.email
    assert str(data[0]["question"]) == "Favourite colour?"
    assert data[0]["answer"] == "Blue"


def test_speaker_question_data_excludes_inactive_questions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target="speaker", active=False)
    AnswerFactory(question=question, speaker=speaker, submission=None)

    _, data = SpeakerQuestionData(event).get_csv_data(_authenticated_request())

    assert data == []


def test_speaker_question_data_excludes_answers_without_speaker():
    """Answers linked to submissions rather than speakers are excluded."""
    event = EventFactory()
    question = QuestionFactory(event=event, target="speaker")
    submission = SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=submission, speaker=None)

    _, data = SpeakerQuestionData(event).get_csv_data(_authenticated_request())

    assert data == []


def test_speaker_question_data_returns_empty_for_anonymous_user():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target="speaker")
    AnswerFactory(question=question, speaker=speaker, submission=None)

    request = RequestFactory().get("/")
    request.user = AnonymousUser()

    _, data = SpeakerQuestionData(event).get_csv_data(request)

    assert data == []


def test_submission_question_data_get_csv_data_returns_submission_answers():
    """Any authenticated user can export all submission answers — access control
    in filter_answers_by_team_access is a no-op for non-anonymous users."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    question = QuestionFactory(
        event=event, target="submission", question="Session level?"
    )
    AnswerFactory(question=question, submission=submission, answer="Beginner")

    field_names, data = SubmissionQuestionData(event).get_csv_data(
        _authenticated_request()
    )

    assert field_names == ["code", "title", "question", "answer"]
    assert len(data) == 1
    assert data[0]["code"] == submission.code
    assert data[0]["title"] == submission.title
    assert str(data[0]["question"]) == "Session level?"
    assert data[0]["answer"] == "Beginner"


def test_submission_question_data_excludes_other_events():
    event = EventFactory()
    other_event = EventFactory()
    question = QuestionFactory(event=other_event, target="submission")
    submission = SubmissionFactory(event=other_event)
    AnswerFactory(question=question, submission=submission)

    _, data = SubmissionQuestionData(event).get_csv_data(_authenticated_request())

    assert data == []


def _authenticated_request():
    request = RequestFactory().get("/")
    request.user = UserFactory.build()
    return request
