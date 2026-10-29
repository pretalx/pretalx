# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    FeedbackFactory,
    ResourceFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def past_slot(published_talk_slot):
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

    with django_assert_num_queries(11):
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
        role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
        speaker = role.speaker
        submission = role.submission
        feedback = FeedbackFactory(
            talk=submission, speaker=speaker, rating=4, review="Excellent!"
        )
    url = event.api_urls.feedback + f"{feedback.pk}/"
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(url, follow=True, headers=headers)
    with_submission = client.get(
        url + "?expand=submission", follow=True, headers=headers
    )
    with_speaker = client.get(url + "?expand=speaker", follow=True, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": feedback.pk,
        "submission": submission.code,
        "speaker": speaker.code,
        "review": "Excellent!",
    }
    assert with_submission.status_code == 200
    data = with_submission.json()["submission"]
    assert data["code"] == submission.code
    assert data["title"] == submission.title
    assert data["state"] == submission.state
    assert with_speaker.status_code == 200
    data = with_speaker.json()["speaker"]
    assert data["code"] == speaker.code
    assert data["name"] == speaker.user.name
    assert "email" not in data


def test_feedback_filter_by_submission(client, event, orga_read_token):
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        unscheduled = SubmissionFactory(event=event)
        feedback1 = FeedbackFactory(talk=sub1)
        FeedbackFactory(talk=sub2)
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(
        event.api_urls.feedback + f"?submission={sub1.code}",
        follow=True,
        headers=headers,
    )
    empty = client.get(
        event.api_urls.feedback + f"?submission={unscheduled.code}",
        follow=True,
        headers=headers,
    )
    invalid = client.get(
        event.api_urls.feedback + "?submission=NONEXISTENT",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert [f["id"] for f in response.json()["results"]] == [feedback1.pk]
    assert empty.status_code == 200
    assert empty.json()["count"] == 0
    assert invalid.status_code == 400


def test_feedback_create_anonymous(client, past_slot):
    submission = past_slot.submission
    event = submission.event
    with scopes_disabled():
        speaker = submission.speakers.first()
        other_speaker = SpeakerFactory(event=event)

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": submission.code,
            "speaker": speaker.code,
            "rating": 999,
            "review": "Amazing talk!",
        },
        content_type="application/json",
    )
    rejected = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": submission.code,
            "speaker": other_speaker.code,
            "review": "Wrong speaker",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    with scopes_disabled():
        feedback = submission.feedback.get()
    assert response.json() == {
        "id": feedback.pk,
        "submission": submission.code,
        "speaker": speaker.code,
        "review": "Amazing talk!",
    }
    assert feedback.rating is None
    assert rejected.status_code == 400
    assert rejected.json() == {
        "speaker": [f"Object with code={other_speaker.code} does not exist."]
    }


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
            "review": "Time traveler feedback",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "submission": ["This session does not accept feedback yet."]
    }


def test_feedback_create_rejects_unscheduled_submission(client):
    event = EventFactory(feature_flags={"use_feedback": True})
    with scopes_disabled():
        submission = SubmissionFactory(event=event)

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": submission.code, "review": "Not scheduled"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "submission": [f"Object with code={submission.code} does not exist."]
    }


def test_feedback_create_denied_when_feature_disabled(client, published_talk_slot):
    event = published_talk_slot.submission.event
    event.feature_flags["use_feedback"] = False
    event.save()

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={
            "submission": published_talk_slot.submission.code,
            "review": "Feature off",
        },
        content_type="application/json",
    )

    assert response.status_code == 403


def test_feedback_delete_requires_write_token(
    client, event, orga_read_token, orga_write_token
):
    with scopes_disabled():
        feedback = FeedbackFactory(talk__event=event)
    url = event.api_urls.feedback + f"{feedback.pk}/"

    rejected = client.delete(
        url, follow=True, headers={"Authorization": f"Token {orga_read_token.token}"}
    )

    assert rejected.status_code == 403
    with scopes_disabled():
        assert feedback.talk.feedback.filter(pk=feedback.pk).exists()

    response = client.delete(
        url, follow=True, headers={"Authorization": f"Token {orga_write_token.token}"}
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not feedback.talk.feedback.filter(pk=feedback.pk).exists()


def test_feedback_create_hidden_schedule_indistinguishable_from_unknown_code(
    client, past_slot
):
    submission = past_slot.submission
    event = submission.event
    event.feature_flags["show_schedule"] = False
    event.save()

    hidden_response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": submission.code, "review": "Hidden schedule"},
        content_type="application/json",
    )
    unknown_response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": "ZZZZZZ", "review": "Hidden schedule"},
        content_type="application/json",
    )

    assert hidden_response.status_code == 400
    assert hidden_response.json() == {
        "submission": [f"Object with code={submission.code} does not exist."]
    }
    assert unknown_response.status_code == 400
    assert unknown_response.json() == {
        "submission": ["Object with code=ZZZZZZ does not exist."]
    }
    with scopes_disabled():
        assert submission.feedback.count() == 0


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
            room=published_talk_slot.submission.slots.select_related("room")
            .first()
            .room,
            schedule=wip_schedule,
            start=now() - timedelta(hours=2),
            end=now() - timedelta(hours=1),
            is_visible=True,
        )

    response = client.post(
        event.api_urls.feedback,
        follow=True,
        data={"submission": new_submission.code, "review": "Unreleased schedule"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_feedback_expanded_submission_shows_internals_to_orga(
    client, event, orga_read_token
):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        internal_tag = TagFactory(event=event, is_public=False)
        submission.tags.add(internal_tag)
        internal_resource = ResourceFactory(submission=submission, is_public=False)
        FeedbackFactory(talk=submission)
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(
        event.api_urls.feedback + "?expand=submission", follow=True, headers=headers
    )
    nested = client.get(
        event.api_urls.feedback + "?expand=submission.submission_type",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["results"][0]["submission"]
    assert data["tags"] == [internal_tag.pk]
    assert data["resources"] == [internal_resource.pk]
    assert nested.status_code == 200
    data = nested.json()["results"][0]["submission"]
    assert data["submission_type"]["id"] == submission.submission_type_id
