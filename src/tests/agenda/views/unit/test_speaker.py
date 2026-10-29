# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import RequestFactory
from django_scopes import scope

from pretalx.agenda.views.speaker import (
    SpeakerList,
    SpeakerSocialMediaCard,
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

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_list_get_queryset_returns_scheduled_speakers_by_name_with_talks(
    published_talk_slot,
):
    event = published_talk_slot.submission.event
    zebra = published_talk_slot.submission.speakers.first()
    zebra.name = "Zebra Speaker"
    zebra.save()
    alpha = SpeakerFactory(event=event, name="Alpha Speaker")
    alpha_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    alpha_sub.speakers.add(alpha)
    TalkSlotFactory(
        submission=alpha_sub, schedule=event.current_schedule, is_visible=True
    )
    unscheduled = SpeakerFactory(event=event)
    unscheduled_sub = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    unscheduled_sub.speakers.add(unscheduled)

    view = make_view(SpeakerList, make_request(event))

    with scope(event=event):
        result = list(view.get_queryset())

    assert result == [alpha, zebra]
    assert result[0].visible_talks == [alpha_sub]
    assert result[1].visible_talks == [published_talk_slot.submission]


def test_speaker_list_get_queryset_search_by_name(published_talk_slot):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()
    speaker.name = "Uniquetestname"
    speaker.save()
    rf = RequestFactory()

    with scope(event=event):
        matching = rf.get("/", {"q": "Uniquetestname"})
        matching.event = event
        found = list(make_view(SpeakerList, matching).get_queryset())
        other = rf.get("/", {"q": "nonexistentnamestring"})
        other.event = event
        not_found = list(make_view(SpeakerList, other).get_queryset())

    assert found == [speaker]
    assert not_found == []


def test_speaker_view_speaker_matches_code_case_insensitively(published_talk_slot):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code.swapcase())

    with scope(event=event):
        result = view.speaker

    assert result == speaker


def test_speaker_view_speaker_returns_none_for_unknown_code(event):
    request = make_request(event)
    view = make_view(SpeakerView, request, code="DOESNTEXIST")

    with scope(event=event):
        result = view.speaker

    assert result is None


def test_speaker_view_get_context_data_categorizes_public_speaker_answers(
    published_talk_slot,
):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()

    def question(**kwargs):
        kwargs = {"target": QuestionTarget.SPEAKER, "is_public": True, **kwargs}
        return QuestionFactory(event=event, **kwargs)

    short_answer = AnswerFactory(
        question=question(variant=QuestionVariant.STRING),
        speaker=speaker,
        submission=None,
    )
    long_answer = AnswerFactory(
        question=question(variant=QuestionVariant.TEXT),
        speaker=speaker,
        submission=None,
    )
    icon_answer = AnswerFactory(
        question=question(variant=QuestionVariant.URL, icon="mastodon"),
        speaker=speaker,
        submission=None,
    )
    AnswerFactory(
        question=question(variant=QuestionVariant.STRING, is_public=False),
        speaker=speaker,
        submission=None,
    )
    AnswerFactory(
        question=QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
            is_public=True,
        ),
        speaker=speaker,
        submission=None,
    )

    request = make_request(event)
    view = make_view(SpeakerView, request, code=speaker.code)

    with scope(event=event):
        ctx = view.get_context_data()

    assert list(ctx["short_answers"]) == [short_answer]
    assert list(ctx["long_answers"]) == [long_answer]
    assert list(ctx["icon_answers"]) == [icon_answer]
    assert ctx["show_sidebar"]
    assert not ctx["show_avatar"]


def test_speaker_social_media_card_get_image_with_avatar_request(published_talk_slot):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()

    request = make_request(event)
    view = make_view(SpeakerSocialMediaCard, request, code=speaker.code)

    with scope(event=event):
        result = view.get_image()

    # No avatar set, so returns the avatar field (which is falsy)
    assert not result


def test_speaker_social_media_card_get_image_without_avatar_request(
    published_talk_slot,
):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()
    cfp = event.cfp
    cfp.fields["avatar"] = {"visibility": "do_not_ask"}
    cfp.save()

    request = make_request(event)
    view = make_view(SpeakerSocialMediaCard, request, code=speaker.code)

    with scope(event=event):
        result = view.get_image()

    assert result is None
