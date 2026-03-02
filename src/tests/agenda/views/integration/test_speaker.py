# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.core.files.storage import Storage
from django.urls import reverse
from django_scopes import scope, scopes_disabled

from pretalx.common.text.path import safe_filename
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import make_published_schedule

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_speaker_list_not_visible_without_schedule(client, event):
    response = client.get(event.urls.speakers, follow=True)

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_query_count(client, event, item_count, django_assert_num_queries):
    make_published_schedule(event, item_count)

    with django_assert_num_queries(9):
        response = client.get(event.urls.speakers, follow=True)

    assert response.status_code == 200
    assert len(response.context["speakers"]) == item_count
    content = response.content.decode()
    with scopes_disabled():
        for speaker in event.speakers:
            assert speaker.get_display_name() in content


def test_speaker_list_search_filters_by_name(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        speaker.name = "Findablename"
        speaker.save()
        other_speaker = SpeakerFactory(event=event, name="Otherperson")
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        other_sub.speakers.add(other_speaker)
        TalkSlotFactory(submission=other_sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v2", notify_speakers=False)

    response = client.get(event.urls.speakers + "?q=Findablename", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Findablename" in content
    assert "Otherperson" not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_page_shows_biography_and_talks(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        speaker.biography = "A very interesting biography."
        speaker.save()
        for _ in range(item_count):
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            sub.speakers.add(speaker)
            TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    url = reverse("agenda:speaker", kwargs={"code": speaker.code, "event": event.slug})
    with django_assert_num_queries(12):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "A very interesting biography." in content
    with scopes_disabled():
        for sub in speaker.submissions.all():
            assert sub.title in content


def test_speaker_page_answer_visibility(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        public_question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            is_public=True,
        )
        AnswerFactory(
            question=public_question,
            speaker=speaker,
            submission=None,
            answer="My public answer",
        )
        private_question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            is_public=False,
        )
        AnswerFactory(
            question=private_question,
            speaker=speaker,
            submission=None,
            answer="My secret answer",
        )

    url = reverse("agenda:speaker", kwargs={"code": speaker.code, "event": event.slug})
    response = client.get(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "My public answer" in content
    assert "My secret answer" not in content


def test_speaker_page_404_for_unknown_speaker(client, public_event_with_schedule):
    url = reverse(
        "agenda:speaker",
        kwargs={"code": "DOESNTEXIST", "event": public_event_with_schedule.slug},
    )
    response = client.get(url, follow=True)

    assert response.status_code == 404


def test_speaker_page_hides_invisible_submissions(
    client, public_event_with_schedule, published_talk_slot, django_assert_num_queries
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        invisible_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        invisible_sub.speakers.add(speaker)
        TalkSlotFactory(submission=invisible_sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v2", notify_speakers=False)
            # Mark the slot invisible after freeze (freeze sets is_visible based on state)
            invisible_sub.slots.filter(schedule=event.current_schedule).update(
                is_visible=False
            )

    url = reverse("agenda:speaker", kwargs={"code": speaker.code, "event": event.slug})
    with django_assert_num_queries(12):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert published_talk_slot.submission.title in content
    assert invisible_sub.title not in content


def test_speaker_redirect_to_public_page(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    url = event.urls.speakers + f"by-id/{speaker.pk}/"
    response = client.get(url)

    assert response.status_code == 302
    target_url = reverse(
        "agenda:speaker", kwargs={"code": speaker.code, "event": event.slug}
    )
    assert response.headers["location"].endswith(target_url)


def test_speaker_redirect_404_for_unpublished_speaker(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        sub.speakers.add(speaker)

    url = reverse(
        "agenda:speaker.redirect", kwargs={"pk": speaker.pk, "event": event.slug}
    )
    response = client.get(url)

    assert response.status_code == 404


def test_speaker_social_media_card_404_when_no_images(
    client, public_event_with_schedule, published_talk_slot, django_assert_num_queries
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    url = reverse(
        "agenda:speaker-social", kwargs={"code": speaker.code, "event": event.slug}
    )
    with django_assert_num_queries(8):
        response = client.get(url, follow=True)

    assert response.status_code == 404


def test_speaker_talks_ical_returns_calendar(
    client, public_event_with_schedule, published_talk_slot, django_assert_num_queries
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        other_sub.speakers.add(other_speaker)
        TalkSlotFactory(submission=other_sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v2", notify_speakers=False)

    url = reverse(
        "agenda:speaker.talks.ical", kwargs={"code": speaker.code, "event": event.slug}
    )
    with django_assert_num_queries(13):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    content = response.content.decode()
    assert "VCALENDAR" in content
    assert published_talk_slot.submission.title in content
    assert other_sub.title not in content
    speaker_name = Storage().get_valid_name(name=speaker.get_display_name())
    expected_filename = f"{event.slug}-{safe_filename(speaker_name)}.ics"
    assert f'filename="{expected_filename}"' in response["Content-Disposition"]


def test_speaker_talks_ical_404_without_current_schedule(client, event, organiser_user):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    client.force_login(organiser_user)
    url = reverse(
        "agenda:speaker.talks.ical", kwargs={"code": speaker.code, "event": event.slug}
    )
    response = client.get(url, follow=True)

    assert response.status_code == 404


def test_speaker_talks_ical_suspicious_name_falls_back_to_code(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        # A whitespace-only name triggers SuspiciousFileOperation in get_valid_name
        speaker.name = "   "
        speaker.save()
        speaker.user.name = "   "
        speaker.user.save(update_fields=["name"])

    url = reverse(
        "agenda:speaker.talks.ical", kwargs={"code": speaker.code, "event": event.slug}
    )
    response = client.get(url, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    safe_code = Storage().get_valid_name(name=speaker.code)
    assert safe_code in response["Content-Disposition"]


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.parametrize(
    "primary_color", ("#ff0000", None), ids=["custom_color", "default_color"]
)
def test_empty_avatar_view_color(client, public_event_with_schedule, primary_color):
    event = public_event_with_schedule
    event.primary_color = primary_color
    event.save()
    expected_color = primary_color or settings.DEFAULT_EVENT_PRIMARY_COLOR

    url = event.urls.speakers + "avatar.svg"
    response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    content = b"".join(response.streaming_content).decode()
    assert expected_color in content
    assert "<svg" in content
