# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.api.serializers.speaker import (
    SpeakerOrgaSerializer,
    SpeakerSerializer,
    SpeakerUpdateSerializer,
)
from pretalx.submission.models import QuestionTarget
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
)
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def make_context(event=None, submissions=None, questions=None, **request_kwargs):
    return {
        "request": make_api_request(event=event, **request_kwargs),
        "submissions": submissions,
        "questions": questions or [],
    }


@pytest.mark.parametrize(
    ("visibility", "expected_present"), (("optional", True), ("do_not_ask", False))
)
def test_speaker_serializer_init_avatar_url_field_presence(
    visibility, expected_present
):
    event = EventFactory(cfp__fields={"avatar": {"visibility": visibility}})
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert ("avatar_url" in serializer.fields) is expected_present


@pytest.mark.parametrize(
    ("speaker_name", "user_name", "expected"),
    (("Speaker Name", "Real Name", "Speaker Name"), ("", "User Name", "User Name")),
)
def test_speaker_serializer_to_representation_display_name(
    speaker_name, user_name, expected
):
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__name=user_name, name=speaker_name)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["name"] == expected


def test_speaker_serializer_get_submissions_empty_without_context():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["submissions"] == []


def test_speaker_serializer_get_submissions_returns_codes():
    event = EventFactory()
    role = SpeakerRoleFactory(submission__event=event, speaker__event=event)

    context = make_context(event=event, submissions=True)
    serializer = SpeakerSerializer(role.speaker, context=context)

    assert serializer.data["submissions"] == [role.submission.code]


def test_speaker_serializer_get_answers_empty_without_questions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["answers"] == []


def test_speaker_serializer_get_answers_filters_speaker_questions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    speaker_question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, position=1
    )
    submission_question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, position=2
    )
    speaker_answer = AnswerFactory(
        question=speaker_question, speaker=speaker, submission=None
    )
    AnswerFactory(question=submission_question, speaker=speaker, submission=None)

    context = make_context(
        event=event, questions=[speaker_question, submission_question]
    )
    serializer = SpeakerSerializer(speaker, context=context)

    assert serializer.data["answers"] == [speaker_answer.pk]


def test_speaker_serializer_get_answers_sorted_by_question_position():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    q1 = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=10)
    q2 = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=1)
    a1 = AnswerFactory(question=q1, speaker=speaker, submission=None)
    a2 = AnswerFactory(question=q2, speaker=speaker, submission=None)

    context = make_context(event=event, questions=[q1, q2])
    serializer = SpeakerSerializer(speaker, context=context)

    assert serializer.data["answers"] == [a2.pk, a1.pk]


def test_speaker_serializer_update_without_availabilities():
    event = EventFactory()
    speaker = SpeakerFactory(event=event, biography="Old bio")

    serializer = SpeakerSerializer(
        speaker,
        data={"biography": "New bio"},
        partial=True,
        context=make_context(event=event),
    )
    serializer.is_valid(raise_exception=True)
    result = serializer.save()

    result.refresh_from_db()
    assert result.biography == "New bio"


def test_speaker_orga_serializer_includes_orga_fields():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    for field in ("email", "timezone", "locale", "has_arrived", "internal_notes"):
        assert field in serializer.fields


def test_speaker_orga_serializer_removes_availabilities_when_not_requested():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    assert "availabilities" not in serializer.fields


def test_speaker_orga_serializer_makes_availabilities_required_when_cfp_requires():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    assert serializer.fields["availabilities"].required is True


def test_speaker_orga_serializer_without_event_keeps_all_fields():
    speaker = SpeakerFactory()

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=None))

    assert "availabilities" in serializer.fields


def test_speaker_update_serializer_removes_avatar_when_not_requested():
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(speaker, context=make_context(event=event))

    assert "avatar" not in serializer.fields


def test_speaker_update_serializer_email_is_read_only():
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__email="mine@example.com")

    serializer = SpeakerUpdateSerializer(
        speaker,
        data={"email": "new@example.com", "biography": "New bio"},
        context=make_context(event=event),
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    assert "email" not in serializer.validated_data
    assert "user" not in serializer.validated_data
    serializer.save()

    speaker.user.refresh_from_db()
    speaker.refresh_from_db()
    assert speaker.user.email == "mine@example.com"
    assert speaker.biography == "New bio"


def test_speaker_update_serializer_update_with_avatar(make_image):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    assert speaker.profile_picture is None

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    serializer.update(speaker, {"avatar": make_image("avatar.png")})

    speaker.refresh_from_db()
    assert speaker.profile_picture is not None


def test_speaker_update_serializer_update_without_avatar():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    serializer.update(speaker, {"biography": "updated"})

    speaker.refresh_from_db()
    assert speaker.profile_picture is None
    assert speaker.biography == "updated"


def test_speaker_orga_serializer_update_with_availabilities():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=2)

    serializer = SpeakerOrgaSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    serializer.update(speaker, {"availabilities": [{"start": start, "end": end}]})

    avails = list(speaker.availabilities.all())
    assert len(avails) == 1
    assert avails[0].start == start
    assert avails[0].end == end
    assert avails[0].person == speaker
    assert avails[0].event == event


def test_speaker_serializer_get_submissions_expanded():
    event = EventFactory()
    role = SpeakerRoleFactory(submission__event=event, speaker__event=event)

    context = make_context(
        event=event, submissions=True, data={"expand": "submissions"}
    )
    serializer = SpeakerSerializer(role.speaker, context=context)

    data = serializer.data

    assert len(data["submissions"]) == 1
    assert data["submissions"][0]["code"] == role.submission.code


def test_speaker_serializer_get_answers_expanded():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=1)
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    context = make_context(
        event=event, questions=[question], data={"expand": "answers"}
    )
    serializer = SpeakerSerializer(speaker, context=context)

    data = serializer.data

    assert len(data["answers"]) == 1
    assert data["answers"][0]["id"] == answer.pk
