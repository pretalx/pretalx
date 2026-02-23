# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.api.serializers.feedback import FeedbackSerializer
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Feedback


@pytest.mark.django_db
def test_feedback_serializer(feedback):
    with scope(event=feedback.talk.event):
        data = FeedbackSerializer(feedback).data
        assert set(data.keys()) == {"id", "submission", "speaker", "rating", "review"}
        assert data["submission"] == feedback.talk.code
        assert data["speaker"] is None
        assert data["review"] == "I liked it!"


@pytest.mark.django_db
def test_anon_cannot_list_feedback(client, event, feedback):
    response = client.get(event.api_urls.feedback, follow=True)
    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_orga_can_list_feedback(
    client, orga_user_token, event, feedback, django_assert_num_queries, item_count
):
    if item_count == 2:
        with scope(event=event):
            Feedback.objects.create(talk=feedback.talk, review="Also great!")

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.feedback,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert len(content["results"]) == item_count
    assert feedback.pk in [r["id"] for r in content["results"]]


@pytest.mark.django_db
def test_orga_can_filter_feedback_by_submission(
    client, orga_user_token, event, feedback, past_slot
):
    response = client.get(
        event.api_urls.feedback + f"?submission={past_slot.submission.code}",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert len(content["results"]) == 1
    assert content["results"][0]["id"] == feedback.pk


@pytest.mark.django_db
def test_orga_can_filter_feedback_by_unscheduled_submission(
    client, orga_user_token, event, feedback, submission
):
    # The submission fixture is not in the schedule, so there's no feedback for it
    response = client.get(
        event.api_urls.feedback + f"?submission={submission.code}",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert len(content["results"]) == 0


@pytest.mark.django_db
def test_orga_filter_by_invalid_submission_code_returns_error(
    client, orga_user_token, event, feedback
):
    # Filtering by a submission code that doesn't exist should return an error
    response = client.get(
        event.api_urls.feedback + "?submission=NONEXISTENT",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    # The filter should return 400 because the code is invalid
    assert response.status_code == 400, content


@pytest.mark.django_db
def test_orga_can_see_expanded_feedback_submission(
    client, orga_user_token, event, feedback
):
    response = client.get(
        event.api_urls.feedback + "?expand=submission,submission.submission_type",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert len(content["results"]) == 1
    data = content["results"][0]
    assert data["submission"]["code"] == feedback.talk.code
    assert "title" in data["submission"]
    assert "state" in data["submission"]
    assert "name" in data["submission"]["submission_type"]


@pytest.mark.django_db
def test_orga_can_see_expanded_feedback_speaker(
    client, orga_user_token, event, feedback, past_slot, speaker, speaker_profile
):
    with scope(event=event):
        past_slot.submission.speakers.add(speaker_profile)
        feedback.speaker = speaker_profile
        feedback.save()

    response = client.get(
        event.api_urls.feedback + "?expand=speaker",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert len(content["results"]) == 1
    data = content["results"][0]
    assert data["speaker"]["code"] == speaker_profile.code
    assert data["speaker"]["name"] == speaker_profile.get_display_name()
    assert "email" not in data["speaker"]


@pytest.mark.django_db
def test_anon_cannot_see_feedback_detail(client, event, feedback):
    response = client.get(event.api_urls.feedback + f"{feedback.pk}/", follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_orga_can_see_feedback_detail(client, orga_user_token, event, feedback):
    response = client.get(
        event.api_urls.feedback + f"{feedback.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = json.loads(response.text)

    assert response.status_code == 200
    assert content["id"] == feedback.pk
    assert content["submission"] == feedback.talk.code


@pytest.mark.django_db
def test_anon_can_create_feedback(client, event, past_slot):
    url = event.api_urls.feedback
    data = {
        "submission": past_slot.submission.code,
        "review": "Great talk!",
        "rating": 5,
    }

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == 201, response.text

    with scope(event=event):
        new_feedback = Feedback.objects.get(talk=past_slot.submission)
        assert new_feedback.review == data["review"]
        assert new_feedback.rating == data["rating"]


@pytest.mark.django_db
def test_anon_can_create_feedback_without_rating(client, event, past_slot):
    url = event.api_urls.feedback
    data = {"submission": past_slot.submission.code, "review": "Great talk!"}

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == 201, response.text

    with scope(event=event):
        new_feedback = Feedback.objects.get(talk=past_slot.submission)
        assert new_feedback.review == data["review"]
        assert new_feedback.rating is None


@pytest.mark.django_db
def test_anon_can_create_feedback_with_speaker(client, event, past_slot, speaker):
    with scope(event=event):
        profile, _ = SpeakerProfile.objects.get_or_create(user=speaker, event=event)
        past_slot.submission.speakers.add(profile)

    url = event.api_urls.feedback
    data = {
        "submission": past_slot.submission.code,
        "review": "Great speaker!",
        "speaker": profile.code,
    }

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == 201, response.text

    with scope(event=event):
        new_feedback = Feedback.objects.get(talk=past_slot.submission)
        assert new_feedback.speaker == profile


@pytest.mark.django_db
def test_anon_cannot_create_feedback_with_unrelated_speaker(
    client, event, past_slot, speaker
):
    # The speaker has a profile but is not a speaker of the submission
    with scope(event=event):
        profile, _ = SpeakerProfile.objects.get_or_create(user=speaker, event=event)
    url = event.api_urls.feedback
    data = {
        "submission": past_slot.submission.code,
        "review": "Great speaker!",
        "speaker": profile.code,
    }

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    content = json.loads(response.text)

    assert response.status_code == 400, content
    assert "speaker" in content


@pytest.mark.django_db
def test_anon_cannot_create_feedback_for_unscheduled_submission(
    client, event, submission
):
    # The `submission` fixture is not in the schedule
    url = event.api_urls.feedback
    data = {"submission": submission.code, "review": "Great talk!"}

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    # Should fail because the submission is not in event.talks
    assert response.status_code == 400, response.text


@pytest.mark.django_db
def test_anon_cannot_create_feedback_for_future_session(client, event, slot):
    # Set the slot to start in the future
    with scope(event=event):
        slot.start = now() + dt.timedelta(hours=1)
        slot.end = now() + dt.timedelta(hours=2)
        slot.save()

    url = event.api_urls.feedback
    data = {"submission": slot.submission.code, "review": "Great talk!"}

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    content = json.loads(response.text)

    # Should fail because the session hasn't started yet
    assert response.status_code == 400, content
    assert "submission" in content


@pytest.mark.django_db
def test_anon_cannot_create_feedback_for_unreleased_schedule(
    client, event, unreleased_slot
):
    # The `unreleased_slot` fixture is in the WIP schedule, not released
    url = event.api_urls.feedback
    data = {"submission": unreleased_slot.submission.code, "review": "Great talk!"}

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    # Should fail because the submission is not in the released schedule
    assert response.status_code == 400, response.text


@pytest.mark.django_db
def test_anon_cannot_create_feedback_when_disabled_in_settings(
    client, event, past_slot
):
    with scope(event=event):
        event.feature_flags["use_feedback"] = False
        event.save()

    url = event.api_urls.feedback
    data = {"submission": past_slot.submission.code, "review": "Great talk!"}

    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == 403, response.text


@pytest.mark.django_db
def test_anon_cannot_delete_feedback(client, event, feedback):
    url = event.api_urls.feedback + f"{feedback.pk}/"
    response = client.delete(url)
    assert response.status_code == 404, response.text


@pytest.mark.django_db
def test_orga_can_delete_feedback(client, orga_user_token, event, feedback):
    orga_user_token.endpoints["feedback"] = ["list", "retrieve", "destroy"]
    orga_user_token.save()

    with scope(event=event):
        feedback_pk = feedback.pk
        assert Feedback.objects.filter(pk=feedback_pk).exists()
        url = event.api_urls.feedback + f"{feedback_pk}/"

    response = client.delete(
        url, headers={"Authorization": f"Token {orga_user_token.token}"}
    )
    assert response.status_code == 204, response.text

    with scope(event=event):
        assert not Feedback.objects.filter(pk=feedback_pk).exists()
