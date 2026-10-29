# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from pretalx.submission.interfaces.exporters import (
    SpeakerQuestionData,
    SubmissionQuestionData,
)
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


def _orga_request(event):
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    request = RequestFactory().get("/")
    request.user = user
    return request


def test_speaker_question_data_get_csv_data_lists_visible_active_speaker_answers():
    event = EventFactory()
    speaker = SpeakerFactory(event=event, name="Alice")
    managed = SpeakerFactory(event=event, user=None, name="Managed Speaker")
    question = QuestionFactory(
        event=event, target="speaker", question="Favourite colour?"
    )
    AnswerFactory(question=question, speaker=speaker, submission=None, answer="Blue")
    AnswerFactory(question=question, speaker=managed, submission=None, answer="Red")
    inactive = QuestionFactory(event=event, target="speaker", active=False)
    AnswerFactory(question=inactive, speaker=speaker, submission=None, answer="Old")
    restricted = QuestionFactory(event=event, target="speaker", question="Hidden")
    restricted.limit_teams.add(TeamFactory(organiser=event.organiser, all_events=True))
    AnswerFactory(question=restricted, speaker=speaker, submission=None, answer="H")
    AnswerFactory(
        question=question,
        submission=SubmissionFactory(event=event),
        speaker=None,
        answer="No speaker",
    )
    exporter = SpeakerQuestionData(ScheduleFactory.build(event=event))
    anonymous_request = RequestFactory().get("/")
    anonymous_request.user = AnonymousUser()

    field_names, data = exporter.get_csv_data(_orga_request(event))
    _, anonymous_data = exporter.get_csv_data(anonymous_request)

    assert field_names == ["code", "name", "email", "question", "answer"]
    assert data == [
        {
            "code": speaker.code,
            "name": "Alice",
            "email": speaker.user.email,
            "question": "Favourite colour?",
            "answer": "Blue",
        },
        {
            "code": managed.code,
            "name": "Managed Speaker",
            "email": "",
            "question": "Favourite colour?",
            "answer": "Red",
        },
    ]
    assert anonymous_data == []


def test_submission_question_data_get_csv_data_lists_this_events_answers():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    question = QuestionFactory(
        event=event, target="submission", question="Session level?"
    )
    AnswerFactory(question=question, submission=submission, answer="Beginner")
    other_event = EventFactory()
    AnswerFactory(
        question=QuestionFactory(event=other_event, target="submission"),
        submission=SubmissionFactory(event=other_event),
        answer="Elsewhere",
    )

    field_names, data = SubmissionQuestionData(
        ScheduleFactory.build(event=event)
    ).get_csv_data(_orga_request(event))

    assert field_names == ["code", "title", "question", "answer"]
    assert data == [
        {
            "code": submission.code,
            "title": submission.title,
            "question": "Session level?",
            "answer": "Beginner",
        }
    ]
