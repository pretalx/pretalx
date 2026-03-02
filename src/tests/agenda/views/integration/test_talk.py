# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils import formats
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.agenda.recording import BaseRecordingProvider
from pretalx.agenda.signals import register_recording_provider
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def second_talk(event):
    """A second confirmed talk on the same event (for cross-referencing)."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
    return submission


@pytest.fixture
def feedback_submission(event):
    """A past confirmed talk on a public event with feedback enabled and
    a released schedule. Returns the submission."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=now() - dt.timedelta(hours=2),
            end=now() - dt.timedelta(hours=1),
        )
        event.wip_schedule.freeze("v1", notify_speakers=False)
    return submission


def test_talk_view_default_rendering(
    client, django_assert_num_queries, published_talk_slot
):
    """Talk detail page renders title, abstract, description, schedule details,
    and no edit/recording/do-not-record indicators for anonymous users."""
    slot = published_talk_slot
    submission = slot.submission
    with scopes_disabled():
        submission.abstract = "Test abstract for the talk"
        submission.description = "Test description for the talk"
        submission.save()

    with django_assert_num_queries(17):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert content.count(submission.title) >= 2  # meta + heading
    assert submission.abstract in content
    assert submission.description in content
    with scopes_disabled():
        assert formats.date_format(slot.local_start, "H:i") in content
        assert formats.date_format(slot.local_end, "H:i") in content
        assert str(slot.room.name) in content
    assert "fa-edit" not in content
    assert "fa-video" not in content
    assert "<iframe" not in content


def test_talk_view_404_for_nonpublic_event(client, django_assert_num_queries):
    with scopes_disabled():
        event = EventFactory(is_public=False)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(9):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 404


def test_talk_view_404_for_other_events_submission(
    client, django_assert_num_queries, event
):
    with scopes_disabled():
        other_submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    url = f"/{event.slug}/talk/{other_submission.code}/"

    with django_assert_num_queries(6):
        response = client.get(url, follow=True)

    assert response.status_code == 404


def test_talk_view_orga_can_see_unreleased(
    client, django_assert_num_queries, event, organiser_user
):
    """Organisers can see talks even before the schedule is released,
    but schedule details (time, room) are not shown."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
    client.force_login(organiser_user)

    with django_assert_num_queries(20):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content
    with scopes_disabled():
        assert formats.date_format(slot.local_start, "H:i") not in content
        assert str(slot.room.name) not in content


def test_talk_view_visibility_by_state_returns_404(
    client, django_assert_num_queries, event
):
    """Non-confirmed submissions are not visible in the public agenda,
    even with a released schedule."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)
        Submission.objects.filter(pk=submission.pk).update(
            state=SubmissionStates.WITHDRAWN
        )
        submission.slots.filter(schedule=event.current_schedule).update(
            is_visible=False
        )

    with django_assert_num_queries(11):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 404


def test_talk_view_shows_edit_button_for_speaker(
    client, django_assert_num_queries, published_talk_slot
):
    slot = published_talk_slot
    with scopes_disabled():
        speaker_user = slot.submission.speakers.first().user
    client.force_login(speaker_user)

    with django_assert_num_queries(20):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-edit" in response.content.decode()


def test_talk_view_shows_do_not_record_indicator(
    client, django_assert_num_queries, published_talk_slot
):
    slot = published_talk_slot
    with scopes_disabled():
        slot.submission.do_not_record = True
        slot.submission.save()

    with django_assert_num_queries(17):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-video" in response.content.decode()


def test_talk_view_feedback_link_shown_for_past_talk(
    client, django_assert_num_queries, feedback_submission
):
    with django_assert_num_queries(17):
        response = client.get(feedback_submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-comments" in response.content.decode()


def test_talk_view_recording_iframe_with_plugin(
    client, django_assert_num_queries, register_signal_handler, published_talk_slot
):
    """When a recording provider plugin returns an iframe, it's shown and
    the CSP header is updated to allow the provider's domain."""
    slot = published_talk_slot

    class TestProvider(BaseRecordingProvider):
        def get_recording(self, sub):
            return {"iframe": "<iframe src='video'></iframe>", "csp_header": "cdn.test"}

    def handler(signal, sender, **kwargs):
        return TestProvider(sender)

    register_signal_handler(register_recording_provider, handler)

    with django_assert_num_queries(17):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "<iframe" in response.content.decode()
    assert response._csp_update == {"frame-src": "cdn.test"}


def test_talk_view_shows_public_resources_only(
    client, django_assert_num_queries, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)
        public_resource = ResourceFactory(
            submission=submission,
            link="https://example.com/public",
            description="Public slides",
            is_public=True,
        )
        private_resource = ResourceFactory(
            submission=submission,
            link="https://example.com/private",
            description="Private notes",
            is_public=False,
        )

    with django_assert_num_queries(17):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert public_resource.link in content
    assert private_resource.link not in content


def test_talk_view_speaker_other_submissions(
    client, django_assert_num_queries, published_talk_slot, second_talk
):
    slot = published_talk_slot
    event = slot.submission.event
    with scopes_disabled():
        speaker = slot.submission.speakers.first()
        second_talk.speakers.add(speaker)
        event.wip_schedule.freeze("v2", notify_speakers=False)

    with django_assert_num_queries(17):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    speakers = response.context["speakers"]
    speaker_data = next(s for s in speakers if s.pk == speaker.pk)
    assert len(speaker_data.other_submissions) == 1
    assert speaker_data.other_submissions[0].pk == second_talk.pk


def test_talk_view_context_without_schedule_permission(
    client, django_assert_num_queries
):
    event = EventFactory(feature_flags={"show_featured": "always"})
    organiser_user = make_orga_user(event)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, is_featured=True
        )
        submission.speakers.add(speaker)
    client.force_login(organiser_user)

    with django_assert_num_queries(19):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    speakers = response.context["speakers"]
    assert len(speakers) == 1
    assert speakers[0].pk == speaker.pk


def test_talk_view_speaker_other_submissions_excludes_invisible_slots(
    client, django_assert_num_queries, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        visible_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        visible_sub.speakers.add(speaker)
        TalkSlotFactory(submission=visible_sub, is_visible=True)
        hidden_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        hidden_sub.speakers.add(speaker)
        TalkSlotFactory(submission=hidden_sub, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)
        hidden_sub.slots.filter(schedule=event.current_schedule).update(
            is_visible=False
        )

    with django_assert_num_queries(17):
        response = client.get(visible_sub.urls.public, follow=True)

    assert response.status_code == 200
    speakers = response.context["speakers"]
    assert len(speakers) == 1
    assert len(speakers[0].other_submissions) == 0


@pytest.mark.parametrize("item_count", (1, 3))
def test_talk_view_speaker_query_count(
    client, django_assert_num_queries, event, item_count
):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        speakers = SpeakerFactory.create_batch(item_count, event=event)
        submission.speakers.add(*speakers)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(17):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    with scopes_disabled():
        for speaker in speakers:
            assert speaker.get_display_name() in content


def test_talk_social_media_card_404_without_image(
    client, django_assert_num_queries, published_talk_slot
):
    slot = published_talk_slot

    with django_assert_num_queries(11):
        response = client.get(slot.submission.urls.social_image, follow=True)

    assert response.status_code == 404


def test_talk_review_view_renders_when_enabled(client, django_assert_num_queries):
    event = EventFactory(feature_flags={"submission_public_review": True})
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)

    with django_assert_num_queries(16):
        response = client.get(submission.urls.review, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_single_ical_view_returns_calendar(
    client, django_assert_num_queries, published_talk_slot
):
    slot = published_talk_slot
    submission = slot.submission

    with django_assert_num_queries(11):
        response = client.get(submission.urls.ical, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    assert "VCALENDAR" in response.content.decode()
    disposition = response["Content-Disposition"]
    assert submission.code in disposition
    assert submission.event.slug in disposition


def test_feedback_view_accessible_for_past_talk(
    client, django_assert_num_queries, feedback_submission
):
    with django_assert_num_queries(12):
        response = client.get(feedback_submission.urls.feedback, follow=True)

    assert response.status_code == 200
    assert "review" in response.context["form"].fields


def test_feedback_view_submit_creates_feedback(
    client, django_assert_num_queries, feedback_submission
):
    with django_assert_num_queries(37):
        response = client.post(
            feedback_submission.urls.feedback, {"review": "Great talk!"}, follow=True
        )

    assert response.status_code == 200
    with scopes_disabled():
        feedback = feedback_submission.feedback.first()
        assert feedback is not None
        assert feedback.review == "Great talk!"
        assert feedback.speaker == feedback_submission.speakers.first()


def test_feedback_view_submit_multiple_speakers_no_auto_assign(
    client, django_assert_num_queries, feedback_submission
):
    with scopes_disabled():
        speaker2 = SpeakerFactory(event=feedback_submission.event)
        feedback_submission.speakers.add(speaker2)

    with django_assert_num_queries(37):
        response = client.post(
            feedback_submission.urls.feedback, {"review": "Great talks!"}, follow=True
        )

    assert response.status_code == 200
    with scopes_disabled():
        feedback = feedback_submission.feedback.first()
        assert feedback is not None
        assert feedback.review == "Great talks!"
        assert feedback.speaker is None


def test_feedback_view_rejects_post_before_talk_starts(
    client, django_assert_num_queries, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=now() + dt.timedelta(hours=1),
            end=now() + dt.timedelta(hours=2),
        )
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(12):
        response = client.post(
            submission.urls.feedback, {"review": "Time traveler!"}, follow=True
        )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.feedback.count() == 0


def test_feedback_view_honeypot_rejects_spam(
    client, django_assert_num_queries, feedback_submission
):
    with django_assert_num_queries(12):
        response = client.post(
            feedback_submission.urls.feedback,
            {"review": "Buy my stuff!", "subject": "on"},
            follow=True,
        )

    assert response.status_code == 200
    with scopes_disabled():
        assert feedback_submission.feedback.count() == 0


def test_feedback_view_speaker_sees_feedback(
    client, django_assert_num_queries, feedback_submission
):
    with scopes_disabled():
        FeedbackFactory(talk=feedback_submission, review="Loved it!")
        speaker_user = feedback_submission.speakers.first().user
    client.force_login(speaker_user)

    with django_assert_num_queries(16):
        response = client.get(feedback_submission.urls.feedback)

    assert response.status_code == 200
    assert "Loved it!" in response.content.decode()


def test_feedback_view_redirects_to_talk_after_submit(
    client, django_assert_num_queries, feedback_submission
):
    with django_assert_num_queries(16):
        response = client.post(
            feedback_submission.urls.feedback, {"review": "Nice!"}, follow=False
        )

    assert response.status_code == 302
    assert response.url == feedback_submission.urls.public


def test_feedback_view_accessible_before_talk_starts(
    client, django_assert_num_queries, event
):
    """Feedback form page is accessible (GET) before talk starts, but
    submission is rejected by the form_valid permission check."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=now() + dt.timedelta(hours=1),
            end=now() + dt.timedelta(hours=2),
        )
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(12):
        response = client.get(submission.urls.feedback, follow=True)

    assert response.status_code == 200
    assert "review" in response.context["form"].fields
