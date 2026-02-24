import pytest
from django.db.utils import IntegrityError
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled

from pretalx.person.models.profile import SpeakerProfile
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_speaker_profile_str():
    speaker = SpeakerFactory(name="Alice")
    assert str(speaker) == f"SpeakerProfile(event={speaker.event.slug}, user=Alice)"


@pytest.mark.django_db
def test_speaker_profile_str_unnamed():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = ""
    expected = (
        f"SpeakerProfile(event={speaker.event.slug}, user={speaker.get_display_name()})"
    )
    assert str(speaker) == expected


@pytest.mark.django_db
def test_speaker_profile_get_display_name_profile_name():
    speaker = SpeakerFactory(name="Profile Name")
    assert speaker.get_display_name() == "Profile Name"


@pytest.mark.django_db
def test_speaker_profile_get_display_name_user_name():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = "User Name"
    assert speaker.get_display_name() == "User Name"


@pytest.mark.django_db
def test_speaker_profile_get_display_name_no_user():
    with scopes_disabled():
        speaker = SpeakerProfile.objects.create(
            event=EventFactory(), user=None, name=None
        )
    assert speaker.get_display_name() == str(_("Unnamed speaker"))


@pytest.mark.django_db
def test_speaker_profile_get_display_name_fallback():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = ""
    assert speaker.get_display_name() == str(_("Unnamed speaker"))


@pytest.mark.parametrize(
    "accessor", ("talks", "current_talk_slots"), ids=["talks", "current_talk_slots"]
)
@pytest.mark.django_db
def test_speaker_profile_no_schedule_returns_empty(event, accessor):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        assert list(getattr(speaker, accessor)) == []


@pytest.mark.django_db
def test_speaker_profile_all_answers_empty(event):
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        assert list(speaker.all_answers) == []


@pytest.mark.django_db
def test_speaker_profile_all_answers_includes_speaker_answers(event):
    speaker = SpeakerFactory(event=event)
    question = QuestionFactory(event=event, target="speaker")
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    with scopes_disabled():
        result = list(speaker.all_answers)

    assert result == [answer]


@pytest.mark.django_db
def test_speaker_profile_all_answers_includes_submission_answers(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    question = QuestionFactory(event=event, target="submission")
    answer = AnswerFactory(question=question, submission=submission, speaker=None)

    with scopes_disabled():
        result = list(speaker.all_answers)

    assert result == [answer]


@pytest.mark.django_db
def test_speaker_profile_reviewer_answers_filters_visible(event):
    speaker = SpeakerFactory(event=event)
    question_visible = QuestionFactory(
        event=event, target="speaker", is_visible_to_reviewers=True
    )
    question_hidden = QuestionFactory(
        event=event, target="speaker", is_visible_to_reviewers=False
    )
    visible_answer = AnswerFactory(
        question=question_visible, speaker=speaker, submission=None
    )
    AnswerFactory(question=question_hidden, speaker=speaker, submission=None)

    with scopes_disabled():
        result = list(speaker.reviewer_answers)

    assert result == [visible_answer]


@pytest.mark.django_db
def test_speaker_profile_get_instance_data_with_pk(event):
    speaker = SpeakerFactory(event=event, name="Alice")
    data = speaker.get_instance_data()

    assert data["name"] == "Alice"
    assert data["email"] == speaker.user.email


@pytest.mark.django_db
def test_speaker_profile_get_instance_data_without_pk():
    """Without a pk, the profile-specific email override is not added."""
    with scopes_disabled():
        speaker = SpeakerProfile(event=EventFactory(), user=None, name=None)
    speaker.pk = None
    data = speaker.get_instance_data()
    assert "email" not in data


@pytest.mark.django_db
def test_speaker_profile_get_instance_data_profile_picture_none(event):
    speaker = SpeakerFactory(event=event)
    data = speaker.get_instance_data()
    assert data["profile_picture"] is None


@pytest.mark.django_db
def test_speaker_profile_unique_event_user():
    speaker = SpeakerFactory()
    with pytest.raises(IntegrityError):
        SpeakerFactory(event=speaker.event, user=speaker.user)


@pytest.mark.django_db
def test_speaker_profile_unique_event_code():
    speaker = SpeakerFactory()
    with pytest.raises(IntegrityError), scopes_disabled():
        SpeakerProfile.objects.create(event=speaker.event, user=None, code=speaker.code)


@pytest.mark.django_db
def test_speaker_profile_get_talk_slots_with_schedule(event):
    """get_talk_slots returns slots when a schedule exists."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    schedule = ScheduleFactory(event=event)
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=event):
        result = list(speaker.get_talk_slots(schedule=schedule))

    assert result == [slot]


@pytest.mark.django_db
def test_speaker_profile_full_availability_empty(event):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        result = speaker.full_availability
    assert result == []


@pytest.mark.django_db
def test_speaker_profile_full_availability_with_data(event):
    speaker = SpeakerFactory(event=event)
    avail = AvailabilityFactory(event=event, person=speaker)

    with scope(event=event):
        result = speaker.full_availability

    assert len(result) == 1
    assert result[0].start == avail.start
    assert result[0].end == avail.end


@pytest.mark.django_db
def test_speaker_profile_full_availability_merges_overlapping(event):
    """Overlapping availabilities are merged into a single range."""
    speaker = SpeakerFactory(event=event)
    start = event.datetime_from
    mid = start + (event.datetime_to - start) / 2
    AvailabilityFactory(event=event, person=speaker, start=start, end=mid)
    AvailabilityFactory(event=event, person=speaker, start=mid, end=event.datetime_to)

    with scope(event=event):
        result = speaker.full_availability

    assert len(result) == 1
    assert result[0].start == start
    assert result[0].end == event.datetime_to
