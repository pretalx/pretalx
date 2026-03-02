# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    FeedbackFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def past_slot(published_talk_slot):
    """Published talk slot with start in the past, enabling feedback creation."""
    with scopes_disabled():
        event = published_talk_slot.submission.event
        event.feature_flags["use_feedback"] = True
        event.save()
        slot = published_talk_slot.submission.slots.filter(
            schedule=event.current_schedule
        ).first()
        slot.start = now() - timedelta(hours=2)
        slot.end = now() - timedelta(hours=1)
        slot.save()
    return published_talk_slot


def test_feedback_list_requires_auth(client, event):
    response = client.get(event.api_urls.feedback, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_feedback_list_with_orga_read_token(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        feedbacks = FeedbackFactory.create_batch(item_count, talk=submission)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.feedback,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count
    assert data["results"][0]["id"] == feedbacks[0].pk
    assert data["results"][0]["review"] == feedbacks[0].review


def test_feedback_detail_with_orga_read_token(client, event, orga_read_token):
    with scopes_disabled():
        feedback = FeedbackFactory(talk__event=event, rating=4, review="Excellent!")

    response = client.get(
        event.api_urls.feedback + f"{feedback.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == feedback.pk
    assert data["rating"] == 4
    assert data["review"] == "Excellent!"


def test_feedback_filter_by_submission(client, event, orga_read_token):
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        feedback1 = FeedbackFactory(talk=sub1)
        FeedbackFactory(talk=sub2)

    response = client.get(
        event.api_urls.feedback + f"?submission={sub1.code}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["id"] == feedback1.pk


def test_feedback_filter_by_unscheduled_submission(client, event, orga_read_token):
    with scopes_disabled():
        unscheduled = SubmissionFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        FeedbackFactory(talk=other_sub)

    response = client.get(
        event.api_urls.feedback + f"?submission={unscheduled.code}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_feedback_create_anonymous(client, past_slot):
    submission = past_slot.submission
    event = submission.event

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": submission.code, "rating": 5, "review": "Amazing talk!"},
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["review"] == "Amazing talk!"
    with scopes_disabled():
        assert submission.feedback.count() == 1


def test_feedback_create_with_speaker(client, past_slot):
    submission = past_slot.submission
    event = submission.event
    with scopes_disabled():
        speaker = submission.speakers.first()

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": submission.code,
            "speaker": speaker.code,
            "rating": 4,
            "review": "Great speaker!",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["speaker"] == speaker.code


def test_feedback_create_rejects_unrelated_speaker(client, past_slot):
    submission = past_slot.submission
    event = submission.event
    with scopes_disabled():
        other_speaker = SpeakerFactory(event=event)

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": submission.code,
            "speaker": other_speaker.code,
            "rating": 3,
            "review": "Wrong speaker",
        },
        content_type="application/json",
    )

    assert response.status_code == 400


def test_feedback_create_rejects_future_session(client, published_talk_slot):
    event = published_talk_slot.submission.event
    event.feature_flags["use_feedback"] = True
    event.save()
    with scopes_disabled():
        slot = published_talk_slot.submission.slots.filter(
            schedule=event.current_schedule
        ).first()
        slot.start = now() + timedelta(hours=1)
        slot.end = now() + timedelta(hours=2)
        slot.save()

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": published_talk_slot.submission.code,
            "rating": 5,
            "review": "Time traveler feedback",
        },
        content_type="application/json",
    )

    assert response.status_code == 400


def test_feedback_create_rejects_unscheduled_submission(client):
    event = EventFactory(feature_flags={"use_feedback": True})
    with scopes_disabled():
        submission = SubmissionFactory(event=event)

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": submission.code, "rating": 5, "review": "Not scheduled"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_feedback_create_denied_when_feature_disabled(client, published_talk_slot):
    event = published_talk_slot.submission.event
    event.feature_flags["use_feedback"] = False
    event.save()

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": published_talk_slot.submission.code,
            "rating": 5,
            "review": "Feature off",
        },
        content_type="application/json",
    )

    assert response.status_code == 403


def test_feedback_delete_with_write_token(client, event, orga_write_token):
    with scopes_disabled():
        feedback = FeedbackFactory(talk__event=event)
        feedback_pk = feedback.pk

    response = client.delete(
        event.api_urls.feedback + f"{feedback_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submissions.first().feedback.filter(pk=feedback_pk).exists()


def test_feedback_delete_rejected_with_read_token(client, event, orga_read_token):
    with scopes_disabled():
        feedback = FeedbackFactory(talk__event=event)

    response = client.delete(
        event.api_urls.feedback + f"{feedback.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert feedback.talk.feedback.filter(pk=feedback.pk).exists()


def test_feedback_create_without_rating(client, past_slot):
    submission = past_slot.submission
    event = submission.event

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": submission.code, "review": "Just a comment, no rating."},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["rating"] is None


def test_feedback_detail_expand_submission(client, event, orga_read_token):
    with scopes_disabled():
        feedback = FeedbackFactory(talk__event=event)

    response = client.get(
        event.api_urls.feedback + f"{feedback.pk}/?expand=submission",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["submission"], dict)
    assert data["submission"]["code"] == feedback.talk.code
    assert "title" in data["submission"]
    assert "state" in data["submission"]


def test_feedback_list_expand_submission_type(client, event, orga_read_token):
    with scopes_disabled():
        FeedbackFactory(talk__event=event)

    response = client.get(
        event.api_urls.feedback + "?expand=submission.submission_type",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_feedback_detail_expand_speaker(client, event, orga_read_token):
    with scopes_disabled():
        role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
        speaker = role.speaker
        submission = role.submission
        feedback = FeedbackFactory(talk=submission, speaker=speaker)

    response = client.get(
        event.api_urls.feedback + f"{feedback.pk}/?expand=speaker",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["speaker"], dict)
    assert data["speaker"]["code"] == speaker.code
    assert "name" in data["speaker"]
    assert "email" not in data["speaker"]


def test_feedback_filter_by_invalid_submission_code(client, event, orga_read_token):
    response = client.get(
        event.api_urls.feedback + "?submission=NONEXISTENT",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 400


def test_feedback_create_rejects_unreleased_schedule(client, published_talk_slot):
    event = published_talk_slot.submission.event
    event.feature_flags["use_feedback"] = True
    event.save()
    with scopes_disabled():
        # Create a new WIP schedule with a slot in the past, but don't release it
        wip_schedule = event.wip_schedule
        new_submission = SubmissionFactory(event=event)
        TalkSlotFactory(
            submission=new_submission,
            room=published_talk_slot.submission.slots.first().room,
            schedule=wip_schedule,
            start=now() - timedelta(hours=2),
            end=now() - timedelta(hours=1),
            is_visible=True,
        )

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": new_submission.code,
            "rating": 5,
            "review": "Unreleased schedule",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
