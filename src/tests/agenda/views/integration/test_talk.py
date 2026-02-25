import datetime as dt

import pytest
from django.utils import formats
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.agenda.recording import BaseRecordingProvider
from pretalx.agenda.signals import register_recording_provider
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    FeedbackFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def published_event_with_talk(public_event_with_schedule, published_talk_slot):
    """The current-schedule slot for a visible talk on a public event.

    Derives from public_event_with_schedule — the event has one visible,
    confirmed talk in a room, with start/end times set."""
    with scopes_disabled():
        return published_talk_slot.submission.slots.get(
            schedule=public_event_with_schedule.current_schedule
        )


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
        event.is_public = True
        event.feature_flags["use_feedback"] = True
        event.save()
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


@pytest.mark.django_db
def test_talk_view_default_rendering(
    client, django_assert_num_queries, published_event_with_talk
):
    """Talk detail page renders title, abstract, description, schedule details,
    and no edit/recording/do-not-record indicators for anonymous users."""
    slot = published_event_with_talk
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


@pytest.mark.django_db
def test_talk_view_404_for_nonpublic_event(client, django_assert_num_queries, event):
    """Talk page returns 404 when event is not public."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)
    event.is_public = False
    event.save()

    with django_assert_num_queries(9):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_view_404_for_other_events_submission(
    client, django_assert_num_queries, event
):
    """Talk page returns 404 when accessing a submission from another event."""
    with scopes_disabled():
        event.is_public = True
        event.save()
        other_submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    url = f"/{event.slug}/talk/{other_submission.code}/"

    with django_assert_num_queries(6):
        response = client.get(url, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_view_404_for_unreleased_submission(
    client, django_assert_num_queries, event
):
    """Talk page returns 404 when there's no released schedule."""
    with scopes_disabled():
        event.is_public = True
        event.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)

    with django_assert_num_queries(10):
        response = client.get(submission.urls.public)

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_view_orga_can_see_unreleased(
    client, django_assert_num_queries, event, organiser_user
):
    """Organisers can see talks even before the schedule is released,
    but schedule details (time, room) are not shown."""
    with scopes_disabled():
        event.is_public = True
        event.save()
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
    ),
    ids=["submitted", "accepted", "rejected", "canceled", "withdrawn"],
)
def test_talk_view_visibility_by_state_returns_404(
    client, django_assert_num_queries, event, state
):
    """Non-confirmed submissions are not visible in the public agenda,
    even with a released schedule."""
    with scopes_disabled():
        event.is_public = True
        event.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)
        Submission.objects.filter(pk=submission.pk).update(state=state)
        submission.slots.filter(schedule=event.current_schedule).update(
            is_visible=False
        )

    with django_assert_num_queries(11):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_view_shows_edit_button_for_speaker(
    client, django_assert_num_queries, published_event_with_talk
):
    """Speakers see the edit button on their own talk page."""
    slot = published_event_with_talk
    with scopes_disabled():
        speaker_user = slot.submission.speakers.first().user
    client.force_login(speaker_user)

    with django_assert_num_queries(20):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-edit" in response.content.decode()


@pytest.mark.django_db
def test_talk_view_shows_do_not_record_indicator(
    client, django_assert_num_queries, published_event_with_talk
):
    """do_not_record flag shows the video-off icon on the talk page."""
    slot = published_event_with_talk
    with scopes_disabled():
        slot.submission.do_not_record = True
        slot.submission.save()

    with django_assert_num_queries(17):
        response = client.get(slot.submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-video" in response.content.decode()


@pytest.mark.django_db
def test_talk_view_feedback_link_shown_for_past_talk(
    client, django_assert_num_queries, feedback_submission
):
    """Feedback link appears when the talk slot is in the past and feedback is enabled."""
    with django_assert_num_queries(17):
        response = client.get(feedback_submission.urls.public, follow=True)

    assert response.status_code == 200
    assert "fa-comments" in response.content.decode()


@pytest.mark.django_db
def test_talk_view_recording_iframe_with_plugin(
    client,
    django_assert_num_queries,
    register_signal_handler,
    published_event_with_talk,
):
    """When a recording provider plugin returns an iframe, it's shown and
    the CSP header is updated to allow the provider's domain."""
    slot = published_event_with_talk

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


@pytest.mark.django_db
def test_talk_view_shows_public_resources_only(
    client, django_assert_num_queries, event
):
    """Talk page shows public resources but not private ones."""
    with scopes_disabled():
        event.is_public = True
        event.save()
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


@pytest.mark.django_db
def test_talk_view_speaker_other_submissions(
    client, django_assert_num_queries, published_event_with_talk, second_talk
):
    """When a speaker has multiple talks, other_submissions is populated."""
    slot = published_event_with_talk
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


@pytest.mark.django_db
def test_talk_view_context_without_schedule_permission(
    client, django_assert_num_queries, event, organiser_user
):
    """When user can't view the schedule, context still includes the submission's speakers."""
    with scopes_disabled():
        event.is_public = True
        event.feature_flags["show_featured"] = "always"
        event.save()
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


@pytest.mark.django_db
def test_talk_view_speaker_other_submissions_excludes_invisible_slots(
    client, django_assert_num_queries, event
):
    """Speaker's other_submissions only include talks with visible slots in the
    current schedule."""
    with scopes_disabled():
        event.is_public = True
        event.save()
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


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_talk_view_speaker_query_count(
    client, django_assert_num_queries, event, item_count
):
    """Query count stays constant regardless of speaker count on a talk."""
    with scopes_disabled():
        event.is_public = True
        event.save()
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        speakers = [SpeakerFactory(event=event) for _ in range(item_count)]
        for speaker in speakers:
            submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(17):
        response = client.get(submission.urls.public, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    with scopes_disabled():
        for speaker in speakers:
            assert speaker.get_display_name() in content


@pytest.mark.django_db
def test_talk_social_media_card_404_without_image(
    client, django_assert_num_queries, published_event_with_talk
):
    """Social media card returns 404 when submission has no image and event has no fallback."""
    slot = published_event_with_talk

    with django_assert_num_queries(11):
        response = client.get(slot.submission.urls.social_image, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("enabled", "expected_status", "expected_queries"),
    ((True, 200, 16), (False, 404, 5)),
    ids=["enabled", "disabled"],
)
def test_talk_review_view_by_feature_flag(
    client, django_assert_num_queries, event, enabled, expected_status, expected_queries
):
    """Review page is accessible only when submission_public_review is enabled."""
    with scopes_disabled():
        event.is_public = True
        event.feature_flags["submission_public_review"] = enabled
        event.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)

    with django_assert_num_queries(expected_queries):
        response = client.get(submission.urls.review, follow=True)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert submission.title in response.content.decode()


@pytest.mark.django_db
def test_single_ical_view_returns_calendar(
    client, django_assert_num_queries, published_event_with_talk
):
    """SingleICalView returns an ICS file with correct content type and filename."""
    slot = published_event_with_talk
    submission = slot.submission

    with django_assert_num_queries(11):
        response = client.get(submission.urls.ical, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    assert "VCALENDAR" in response.content.decode()
    disposition = response["Content-Disposition"]
    assert submission.code in disposition
    assert submission.event.slug in disposition


@pytest.mark.django_db
def test_feedback_view_accessible_for_past_talk(
    client, django_assert_num_queries, feedback_submission
):
    """Feedback form page is accessible when the talk is in the past."""
    with django_assert_num_queries(12):
        response = client.get(feedback_submission.urls.feedback, follow=True)

    assert response.status_code == 200
    assert "review" in response.context["form"].fields


@pytest.mark.django_db
def test_feedback_view_submit_creates_feedback(
    client, django_assert_num_queries, feedback_submission
):
    """Submitting feedback creates a Feedback object with auto-assigned speaker."""
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


@pytest.mark.django_db
def test_feedback_view_submit_multiple_speakers_no_auto_assign(
    client, django_assert_num_queries, feedback_submission
):
    """When there are multiple speakers and none is selected, speaker is left null."""
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


@pytest.mark.django_db
def test_feedback_view_rejects_post_before_talk_starts(
    client, django_assert_num_queries, event
):
    """Feedback cannot be submitted before the talk has started."""
    with scopes_disabled():
        event.is_public = True
        event.feature_flags["use_feedback"] = True
        event.save()
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


@pytest.mark.django_db
def test_feedback_view_honeypot_rejects_spam(
    client, django_assert_num_queries, feedback_submission
):
    """Honeypot field rejects spam submissions."""
    with django_assert_num_queries(12):
        response = client.post(
            feedback_submission.urls.feedback,
            {"review": "Buy my stuff!", "subject": "on"},
            follow=True,
        )

    assert response.status_code == 200
    with scopes_disabled():
        assert feedback_submission.feedback.count() == 0


@pytest.mark.django_db
def test_feedback_view_speaker_sees_feedback(
    client, django_assert_num_queries, feedback_submission
):
    """Speakers can see feedback on their talk."""
    with scopes_disabled():
        FeedbackFactory(talk=feedback_submission, review="Loved it!")
        speaker_user = feedback_submission.speakers.first().user
    client.force_login(speaker_user)

    with django_assert_num_queries(16):
        response = client.get(feedback_submission.urls.feedback)

    assert response.status_code == 200
    assert "Loved it!" in response.content.decode()


@pytest.mark.django_db
def test_feedback_view_redirects_to_talk_after_submit(
    client, django_assert_num_queries, feedback_submission
):
    """After successful feedback submission, user is redirected to the talk page."""
    with django_assert_num_queries(16):
        response = client.post(
            feedback_submission.urls.feedback, {"review": "Nice!"}, follow=False
        )

    assert response.status_code == 302
    assert response.url == feedback_submission.urls.public


@pytest.mark.django_db
def test_feedback_view_accessible_before_talk_starts(
    client, django_assert_num_queries, event
):
    """Feedback form page is accessible (GET) before talk starts, but
    submission is rejected by the form_valid permission check."""
    with scopes_disabled():
        event.is_public = True
        event.feature_flags["use_feedback"] = True
        event.save()
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
