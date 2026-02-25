import datetime as dt

import pytest
from django_scopes import scopes_disabled
from rest_framework import exceptions

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
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


def make_context(event=None, submissions=None, questions=None, **request_kwargs):
    return {
        "request": make_api_request(event=event, **request_kwargs),
        "submissions": submissions,
        "questions": questions or [],
    }


@pytest.fixture
def event_with_cfp():
    """An event with its CfP, allowing tests to modify CfP field settings."""
    event = EventFactory()
    with scopes_disabled():
        cfp = event.cfp
    return event, cfp


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("visibility", "expected_present"), (("optional", True), ("do_not_ask", False))
)
def test_speaker_serializer_init_avatar_url_field_presence(
    event_with_cfp, visibility, expected_present
):
    """avatar_url field presence depends on CfP avatar request setting."""
    event, cfp = event_with_cfp
    cfp.fields["avatar"]["visibility"] = visibility
    with scopes_disabled():
        cfp.save()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert ("avatar_url" in serializer.fields) is expected_present


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("speaker_name", "user_name", "expected"),
    (("Speaker Name", "Real Name", "Speaker Name"), ("", "User Name", "User Name")),
)
def test_speaker_serializer_to_representation_display_name(
    speaker_name, user_name, expected
):
    """to_representation uses get_display_name(), falling back to user name."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__name=user_name, name=speaker_name)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["name"] == expected


@pytest.mark.django_db
def test_speaker_serializer_get_submissions_empty_without_context():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["submissions"] == []


@pytest.mark.django_db
def test_speaker_serializer_get_submissions_returns_codes():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    context = make_context(event=event, submissions=True)
    serializer = SpeakerSerializer(speaker, context=context)

    with scopes_disabled():
        assert serializer.data["submissions"] == [submission.code]


@pytest.mark.django_db
def test_speaker_serializer_get_answers_empty_without_questions():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerSerializer(speaker, context=make_context(event=event))

    assert serializer.data["answers"] == []


@pytest.mark.django_db
def test_speaker_serializer_get_answers_filters_speaker_questions():
    """Only answers for speaker-targeted questions are returned, not submission-targeted."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    speaker_question = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, position=1
    )
    submission_question = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, position=2
    )
    with scopes_disabled():
        speaker_answer = AnswerFactory(
            question=speaker_question, speaker=speaker, submission=None
        )
        AnswerFactory(question=submission_question, speaker=speaker, submission=None)

    context = make_context(
        event=event, questions=[speaker_question, submission_question]
    )
    serializer = SpeakerSerializer(speaker, context=context)

    with scopes_disabled():
        assert serializer.data["answers"] == [speaker_answer.pk]


@pytest.mark.django_db
def test_speaker_serializer_get_answers_sorted_by_question_position():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    q1 = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=10)
    q2 = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=1)
    with scopes_disabled():
        a1 = AnswerFactory(question=q1, speaker=speaker, submission=None)
        a2 = AnswerFactory(question=q2, speaker=speaker, submission=None)

    context = make_context(event=event, questions=[q1, q2])
    serializer = SpeakerSerializer(speaker, context=context)

    with scopes_disabled():
        assert serializer.data["answers"] == [a2.pk, a1.pk]


@pytest.mark.django_db
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
    with scopes_disabled():
        result = serializer.save()

    result.refresh_from_db()
    assert result.biography == "New bio"


@pytest.mark.django_db
def test_speaker_orga_serializer_includes_orga_fields():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    for field in ("email", "timezone", "locale", "has_arrived", "internal_notes"):
        assert field in serializer.fields


@pytest.mark.django_db
def test_speaker_orga_serializer_removes_availabilities_when_not_requested(
    event_with_cfp,
):
    event, cfp = event_with_cfp
    cfp.fields["availabilities"]["visibility"] = "do_not_ask"
    with scopes_disabled():
        cfp.save()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    assert "availabilities" not in serializer.fields


@pytest.mark.django_db
def test_speaker_orga_serializer_makes_availabilities_required_when_cfp_requires(
    event_with_cfp,
):
    event, cfp = event_with_cfp
    cfp.fields["availabilities"]["visibility"] = "required"
    with scopes_disabled():
        cfp.save()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=event))

    assert serializer.fields["availabilities"].required is True


@pytest.mark.django_db
def test_speaker_orga_serializer_without_event_keeps_all_fields():
    """Without an event, __init__ skips CfP-based field removal."""
    speaker = SpeakerFactory()

    serializer = SpeakerOrgaSerializer(speaker, context=make_context(event=None))

    assert "availabilities" in serializer.fields


@pytest.mark.django_db
def test_speaker_update_serializer_removes_avatar_when_not_requested(event_with_cfp):
    """The avatar field only exists on SpeakerUpdateSerializer, not SpeakerOrgaSerializer."""
    event, cfp = event_with_cfp
    cfp.fields["avatar"]["visibility"] = "do_not_ask"
    with scopes_disabled():
        cfp.save()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(speaker, context=make_context(event=event))

    assert "avatar" not in serializer.fields


@pytest.mark.django_db
def test_speaker_update_serializer_validate_email_rejects_duplicate():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    UserFactory(email="taken@example.com")

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )

    with pytest.raises(exceptions.ValidationError):
        serializer.validate_email("TAKEN@example.com")


@pytest.mark.django_db
def test_speaker_update_serializer_validate_email_allows_own_email():
    """Case-insensitive comparison allows the speaker's own email."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__email="mine@example.com")

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )

    result = serializer.validate_email("MINE@EXAMPLE.COM")
    assert result == "mine@example.com"


@pytest.mark.django_db
def test_speaker_update_serializer_validate_email_lowercases():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )

    result = serializer.validate_email("NeW@Example.COM")
    assert result == "new@example.com"


@pytest.mark.django_db
def test_speaker_update_serializer_update_saves_user_fields():
    """update() propagates nested user fields (email) to the User model."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    with scopes_disabled():
        result = serializer.update(
            speaker, {"user": {"email": "updated@example.com"}, "biography": "New bio"}
        )

    result.user.refresh_from_db()
    assert result.user.email == "updated@example.com"
    result.refresh_from_db()
    assert result.biography == "New bio"


@pytest.mark.django_db
def test_speaker_update_serializer_update_with_avatar(make_image):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    assert speaker.profile_picture is None

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    with scopes_disabled():
        serializer.update(speaker, {"avatar": make_image("avatar.png")})

    speaker.refresh_from_db()
    assert speaker.profile_picture is not None


@pytest.mark.django_db
def test_speaker_update_serializer_update_without_avatar():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)

    serializer = SpeakerUpdateSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    with scopes_disabled():
        serializer.update(speaker, {"biography": "updated"})

    speaker.refresh_from_db()
    assert speaker.profile_picture is None
    assert speaker.biography == "updated"


@pytest.mark.django_db
def test_speaker_orga_serializer_update_with_availabilities():
    """update() creates Availability objects via _handle_availabilities."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=2)

    serializer = SpeakerOrgaSerializer(
        speaker, context=make_context(event=event), partial=True
    )
    with scopes_disabled():
        serializer.update(speaker, {"availabilities": [{"start": start, "end": end}]})

        avails = list(speaker.availabilities.all())
    assert len(avails) == 1
    assert avails[0].start == start
    assert avails[0].end == end
    assert avails[0].person == speaker
    assert avails[0].event == event


@pytest.mark.django_db
def test_speaker_serializer_get_submissions_expanded():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    context = make_context(
        event=event, submissions=True, data={"expand": "submissions"}
    )
    serializer = SpeakerSerializer(speaker, context=context)

    with scopes_disabled():
        data = serializer.data

    assert len(data["submissions"]) == 1
    assert data["submissions"][0]["code"] == submission.code


@pytest.mark.django_db
def test_speaker_serializer_get_answers_expanded():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER, position=1)
    with scopes_disabled():
        answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    context = make_context(
        event=event, questions=[question], data={"expand": "answers"}
    )
    serializer = SpeakerSerializer(speaker, context=context)

    with scopes_disabled():
        data = serializer.data

    assert len(data["answers"]) == 1
    assert data["answers"][0]["id"] == answer.pk
