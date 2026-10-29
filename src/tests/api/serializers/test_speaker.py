# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.db.models import Prefetch

from pretalx.api.serializers.speaker import (
    SpeakerCreateSerializer,
    SpeakerOrgaSerializer,
    SpeakerSerializer,
    SpeakerUpdateSerializer,
)
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import QuestionTarget, Submission
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
    ("cfp_fields", "expected"),
    (
        ({"avatar": {"visibility": "do_not_ask"}}, {}),
        (
            {"avatar": {"visibility": "optional"}},
            {"avatar_url": False, "avatar": False},
        ),
        (
            {
                "avatar": {"visibility": "required"},
                "availabilities": {"visibility": "required"},
            },
            {"avatar_url": False, "avatar": True, "availabilities": True},
        ),
    ),
    ids=("not_requested", "optional", "required"),
)
def test_speaker_update_serializer_init_fields_follow_cfp(cfp_fields, expected):
    event = EventFactory(cfp__fields=cfp_fields)
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(speaker, context=make_context(event=event))

    assert {
        name: field.required
        for name, field in serializer.fields.items()
        if name in ("avatar_url", "avatar", "availabilities")
    } == expected


def test_speaker_orga_serializer_without_event_keeps_all_fields():
    speaker = SpeakerFactory()

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=None))

    assert "availabilities" in serializer.fields


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


def test_speaker_serializer_submissions_and_answers_empty_without_context():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["submissions"] == []
    assert serializer.data["answers"] == []


def test_speaker_serializer_get_submissions_codes_and_expanded():
    event = EventFactory()
    role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    speaker = (
        SpeakerProfile.objects.select_related("user")
        .prefetch_related(
            Prefetch(
                "submissions",
                queryset=Submission.objects.select_related(
                    "event", "submission_type", "track"
                ),
            )
        )
        .get(pk=role.speaker.pk)
    )

    codes = SpeakerSerializer(
        speaker, context=make_context(event=event, submissions=True)
    ).data["submissions"]
    expanded = SpeakerSerializer(
        speaker,
        context=make_context(
            event=event, submissions=True, data={"expand": "submissions"}
        ),
    ).data["submissions"]

    assert codes == [role.submission.code]
    assert [submission["code"] for submission in expanded] == [role.submission.code]


def test_speaker_serializer_get_answers_filters_speaker_questions_sorted_by_position():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    late_question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, position=10
    )
    early_question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, position=1
    )
    submission_question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, position=2
    )
    late_answer = AnswerFactory(
        question=late_question, speaker=speaker, submission=None
    )
    early_answer = AnswerFactory(
        question=early_question, speaker=speaker, submission=None
    )
    AnswerFactory(question=submission_question, speaker=speaker, submission=None)
    questions = [late_question, early_question, submission_question]

    pks = SpeakerSerializer(
        speaker, context=make_context(event=event, questions=questions)
    ).data["answers"]
    expanded = SpeakerSerializer(
        speaker,
        context=make_context(
            event=event, questions=questions, data={"expand": "answers"}
        ),
    ).data["answers"]

    assert pks == [early_answer.pk, late_answer.pk]
    assert [answer["id"] for answer in expanded] == [early_answer.pk, late_answer.pk]


def test_speaker_update_serializer_update_without_avatar_or_availabilities():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    serializer.update(speaker, {"biography": "updated"})

    speaker.refresh_from_db()
    assert speaker.profile_picture is None
    assert speaker.biography == "updated"
    assert list(speaker.availabilities.all()) == []


def test_speaker_update_serializer_update_sets_avatar_availabilities_and_name(
    make_image,
):
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__name="", name="")
    user = speaker.user
    start = event.datetime_from
    end = start + dt.timedelta(hours=2)
    assert speaker.profile_picture is None

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    serializer.update(
        speaker,
        {
            "avatar": make_image("avatar.png"),
            "availabilities": [{"start": start, "end": end}],
            "name": "Speaker Name",
        },
    )

    speaker.refresh_from_db()
    user.refresh_from_db()
    assert speaker.profile_picture_id is not None
    assert user.name == "Speaker Name"
    avails = list(speaker.availabilities.all())
    assert len(avails) == 1
    assert avails[0].start == start
    assert avails[0].end == end
    assert avails[0].person_id == speaker.pk
    assert avails[0].event_id == event.pk


@pytest.mark.parametrize(
    ("speaker_kwargs", "expected"),
    (
        (
            {"user": None, "name": "Managed Speaker", "email": "contact@example.com"},
            {
                "email": "contact@example.com",
                "locale": "en",
                "timezone": None,
                "is_managed": True,
            },
        ),
        (
            {"user__email": "account@example.com"},
            {"email": "account@example.com", "is_managed": False},
        ),
        (
            {"user__email": "account@example.com", "email": "contact@example.com"},
            {"email": "contact@example.com", "is_managed": False},
        ),
    ),
    ids=("managed", "account", "contact_overrides_account"),
)
def test_speaker_orga_serializer_effective_values(speaker_kwargs, expected):
    event = EventFactory(locale="en")
    speaker = SpeakerFactory(event=event, **speaker_kwargs)

    data = SpeakerOrgaSerializer(speaker, context=make_context(event=event)).data

    assert {key: data[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("speaker_kwargs", "data", "field", "profile_value", "user_value", "shown"),
    (
        (
            {"user__email": "account@example.com"},
            {"email": "contact@example.com"},
            "email",
            "contact@example.com",
            "account@example.com",
            "contact@example.com",
        ),
        ({"user__locale": "en"}, {"locale": "de"}, "locale", "de", "en", "de"),
        (
            {"locale": "de", "user__locale": "en"},
            {"locale": ""},
            "locale",
            None,
            "en",
            "en",
        ),
    ),
    ids=("email", "locale", "empty_locale_clears_override"),
)
def test_speaker_update_serializer_writes_profile_not_account(
    speaker_kwargs, data, field, profile_value, user_value, shown
):
    event = EventFactory(locales=["en", "de"])
    speaker = SpeakerFactory(event=event, **speaker_kwargs)
    user = speaker.user

    serializer = SpeakerUpdateSerializer(
        speaker, data=data, partial=True, context=make_context(event=event)
    )

    assert serializer.is_valid(), serializer.errors
    result = serializer.save()

    speaker.refresh_from_db()
    user.refresh_from_db()
    speaker.user = user
    speaker.event = event
    assert getattr(speaker, field) == profile_value
    assert getattr(user, field) == user_value
    assert serializer.to_representation(result)[field] == shown


def test_speaker_update_serializer_locale_rejects_unoffered_language():
    event = EventFactory(locales=["en"])
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, data={"locale": "de"}, partial=True, context=make_context(event=event)
    )

    assert not serializer.is_valid()
    assert serializer.errors == {
        "locale": ["This language is not enabled for this event."]
    }


def test_speaker_create_serializer_creates_managed_profile_with_update_fields():
    event = EventFactory()
    serializer = SpeakerCreateSerializer(
        data={
            "name": "New Speaker",
            "email": "new@example.com",
            "biography": "A bio",
            "internal_notes": "notes",
            "has_arrived": True,
        },
        context=make_context(event=event),
    )

    assert serializer.is_valid(), serializer.errors
    profile = serializer.save()

    profile.refresh_from_db()
    assert profile.user is None
    assert profile.origin == SpeakerProfileOrigin.ORGA
    assert profile.name == "New Speaker"
    assert profile.email == "new@example.com"
    assert profile.biography == "A bio"
    assert profile.internal_notes == "notes"
    assert profile.has_arrived is True
    assert (
        profile.logged_actions().filter(action_type="pretalx.speaker.create").exists()
    )


@pytest.mark.parametrize(
    ("data", "error"),
    (
        pytest.param(
            {"email": "new@example.com"}, "This field is required.", id="missing"
        ),
        pytest.param(
            {"email": "new@example.com", "name": "x" * 121},
            "Ensure this value has at most 120 characters (it has 121).",
            id="over-model-max-length",
        ),
    ),
)
def test_speaker_create_serializer_rejects_invalid_name(data, error):
    event = EventFactory()

    serializer = SpeakerCreateSerializer(data=data, context=make_context(event=event))

    assert not serializer.is_valid()
    assert serializer.errors == {"name": [error]}
