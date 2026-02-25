import pytest
from django.test import RequestFactory
from django_scopes import scope, scopes_disabled

from pretalx.agenda.views.speaker import (
    SpeakerList,
    SpeakerSocialMediaCard,
    SpeakerTalksIcalView,
    SpeakerView,
)
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_speaker_list_get_queryset_returns_speakers_in_released_schedule(
    published_talk_slot,
):
    """Only speakers with talks in the released schedule are included."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        # Create a speaker who only submitted but isn't in the released schedule
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        other_sub.speakers.add(other_speaker)

    request = make_request(event)
    view = make_view(SpeakerList, request)

    with scope(event=event):
        result = list(view.get_queryset())

    assert result == [speaker]


@pytest.mark.django_db
def test_speaker_list_get_queryset_attaches_visible_talks(published_talk_slot):
    """Each speaker in the queryset gets a visible_talks attribute with their scheduled talks."""
    event = published_talk_slot.submission.event

    request = make_request(event)
    view = make_view(SpeakerList, request)

    with scope(event=event):
        speakers = list(view.get_queryset())

    assert len(speakers) == 1
    assert len(speakers[0].visible_talks) == 1
    assert speakers[0].visible_talks[0] == published_talk_slot.submission


@pytest.mark.django_db
def test_speaker_list_get_queryset_search_by_name(published_talk_slot):
    """The ?q= parameter filters speakers by name."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        speaker.name = "Uniquetestname"
        speaker.save()

    rf = RequestFactory()
    request = rf.get("/", {"q": "Uniquetestname"})
    request.event = event

    view = make_view(SpeakerList, request)

    with scope(event=event):
        result = list(view.get_queryset())

    assert result == [speaker]


@pytest.mark.django_db
def test_speaker_list_get_queryset_search_excludes_non_matching(published_talk_slot):
    """The ?q= parameter filters out speakers whose name doesn't match."""
    event = published_talk_slot.submission.event

    rf = RequestFactory()
    request = rf.get("/", {"q": "nonexistentnamestring"})
    request.event = event

    view = make_view(SpeakerList, request)

    with scope(event=event):
        result = list(view.get_queryset())

    assert result == []


@pytest.mark.django_db
def test_speaker_list_get_queryset_ordered_by_name(published_talk_slot):
    """Speakers are returned ordered by name."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker1 = published_talk_slot.submission.speakers.first()
        speaker1.name = "Zebra Speaker"
        speaker1.save()

        speaker2 = SpeakerFactory(event=event, name="Alpha Speaker")
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub2.speakers.add(speaker2)
        schedule = event.current_schedule
        TalkSlotFactory(submission=sub2, schedule=schedule, is_visible=True)

    request = make_request(event)
    view = make_view(SpeakerList, request)

    with scope(event=event):
        result = list(view.get_queryset())

    assert result == [speaker2, speaker1]


@pytest.mark.django_db
def test_speaker_view_speaker_returns_profile_by_code(published_talk_slot):
    """The speaker property returns the speaker matching the URL code."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        result = view.speaker

    assert result == speaker


@pytest.mark.django_db
def test_speaker_view_speaker_matches_code_case_insensitively(published_talk_slot):
    """Speaker lookup is case-insensitive."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code.upper())

    with scope(event=event):
        result = view.speaker

    assert result == speaker


@pytest.mark.django_db
def test_speaker_view_speaker_returns_none_for_unknown_code(event):
    """Speaker property returns None for an unknown code."""
    request = make_request(event)
    view = make_view(SpeakerView, request, code="DOESNTEXIST")

    with scope(event=event):
        result = view.speaker

    assert result is None


@pytest.mark.django_db
def test_speaker_view_get_permission_object_returns_speaker(published_talk_slot):
    """get_permission_object returns the speaker profile."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        result = view.get_permission_object()

    assert result == speaker


@pytest.mark.django_db
def test_speaker_view_get_context_data_categorizes_answers(published_talk_slot):
    """Context data splits public speaker answers into short, long, and icon categories."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        short_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            is_public=True,
        )
        long_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.TEXT,
            is_public=True,
        )
        short_answer = AnswerFactory(question=short_q, speaker=speaker, submission=None)
        long_answer = AnswerFactory(question=long_q, speaker=speaker, submission=None)

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert list(ctx["short_answers"]) == [short_answer]
    assert list(ctx["long_answers"]) == [long_answer]
    assert list(ctx["icon_answers"]) == []


@pytest.mark.django_db
def test_speaker_view_get_context_data_excludes_non_public_answers(published_talk_slot):
    """Non-public answers are excluded from context."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        private_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            is_public=False,
        )
        AnswerFactory(question=private_q, speaker=speaker, submission=None)

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert list(ctx["short_answers"]) == []
    assert list(ctx["long_answers"]) == []
    assert list(ctx["icon_answers"]) == []


@pytest.mark.django_db
def test_speaker_view_get_context_data_excludes_submission_target_answers(
    published_talk_slot,
):
    """Answers targeting submissions (not speakers) are excluded."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        sub_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
            is_public=True,
        )
        AnswerFactory(question=sub_q, speaker=speaker, submission=None)

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert list(ctx["short_answers"]) == []


@pytest.mark.django_db
def test_speaker_view_get_context_data_icon_answers(published_talk_slot):
    """URL questions with an icon are categorized as icon_answers, not short_answers."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        icon_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.URL,
            is_public=True,
            icon="mastodon",
        )
        icon_answer = AnswerFactory(question=icon_q, speaker=speaker, submission=None)

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert list(ctx["icon_answers"]) == [icon_answer]
    assert list(ctx["short_answers"]) == []


@pytest.mark.django_db
def test_speaker_view_get_context_data_show_avatar_false_by_default(
    published_talk_slot,
):
    """show_avatar is False when speaker has no avatar or avatar not requested."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert not ctx["show_avatar"]


@pytest.mark.django_db
def test_speaker_view_get_context_data_show_sidebar_with_icon_answers(
    published_talk_slot,
):
    """show_sidebar is truthy when icon_answers are present."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        icon_q = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.URL,
            is_public=True,
            icon="mastodon",
        )
        AnswerFactory(question=icon_q, speaker=speaker, submission=None)

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert ctx["show_sidebar"]


@pytest.mark.django_db
def test_speaker_social_media_card_get_image_with_avatar_request(published_talk_slot):
    """get_image returns speaker avatar when CfP requests avatars."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerSocialMediaCard, request, code=speaker.code)

    with scope(event=event):
        result = view.get_image()

    # No avatar set, so returns the avatar field (which is falsy)
    assert not result


@pytest.mark.django_db
def test_speaker_social_media_card_get_image_without_avatar_request(
    published_talk_slot,
):
    """get_image returns None when CfP doesn't request avatars."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
    with scopes_disabled():
        cfp = event.cfp
        cfp.fields["avatar"] = {"visibility": "do_not_ask"}
        cfp.save()

    request = make_request(event)
    view = make_view(SpeakerSocialMediaCard, request, code=speaker.code)

    with scope(event=event):
        result = view.get_image()

    assert result is None


@pytest.mark.django_db
def test_speaker_ical_view_get_object_returns_speaker_by_code(published_talk_slot):
    """get_object returns the speaker matching the URL code."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerTalksIcalView, request, code=speaker.code)

    with scope(event=event):
        result = view.get_object()

    assert result == speaker
