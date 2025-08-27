import json

import pytest
from django_scopes import scope

from pretalx.submission.models.question import QuestionVisibility


@pytest.mark.django_db
def test_question_api_backwards_compatibility_v1(client, orga_user_token, question):
    """Test that the v1 API includes is_public, active, and visibility fields for backwards compatibility."""
    event = question.event
    with scope(event=event):
        question.visibility = QuestionVisibility.PUBLIC
        question.save()

    response = client.get(
        f"{event.api_urls.questions}{question.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200

    data = json.loads(response.content)

    # All fields should be present in the current API version
    assert "visibility" in data
    assert "is_public" in data
    assert "active" in data

    # Verify backwards compatibility mapping for public question
    assert data["visibility"] == QuestionVisibility.PUBLIC
    assert data["is_public"] is True
    assert data["active"] is True

    # Test with visibility = speakers_organisers
    with scope(event=event):
        question.visibility = QuestionVisibility.SPEAKERS_ORGANISERS
        question.save()

    response = client.get(
        f"{event.api_urls.questions}{question.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200

    data = json.loads(response.content)
    assert data["visibility"] == QuestionVisibility.SPEAKERS_ORGANISERS
    assert data["is_public"] is False
    assert data["active"] is True

    # Test with visibility = organisers_only
    with scope(event=event):
        question.visibility = QuestionVisibility.ORGANISERS_ONLY
        question.save()

    response = client.get(
        f"{event.api_urls.questions}{question.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200

    data = json.loads(response.content)
    assert data["visibility"] == QuestionVisibility.ORGANISERS_ONLY
    assert data["is_public"] is False
    assert data["active"] is True

    # Test with visibility = hidden (inactive)
    with scope(event=event):
        question.visibility = QuestionVisibility.HIDDEN
        question.save()

    response = client.get(
        f"{event.api_urls.questions}{question.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200

    data = json.loads(response.content)
    assert data["visibility"] == QuestionVisibility.HIDDEN
    assert data["is_public"] is False
    assert data["active"] is False


@pytest.mark.django_db
def test_question_api_dev_preview_no_deprecated_fields(
    client, orga_user_token, question
):
    """Test that the DEV_PREVIEW API version does not include the deprecated is_public and active fields."""
    event = question.event
    with scope(event=event):
        question.visibility = QuestionVisibility.PUBLIC
        question.save()

    # Request with DEV_PREVIEW version header
    response = client.get(
        f"{event.api_urls.questions}{question.pk}/",
        follow=True,
        headers={
            "pretalx-version": "DEV_PREVIEW",
            "Authorization": f"Token {orga_user_token.token}",
        },
    )
    assert response.status_code == 200

    data = json.loads(response.content)

    # Only visibility should be present, not the deprecated fields
    assert "visibility" in data
    assert "is_public" not in data
    assert "active" not in data
    assert data["visibility"] == QuestionVisibility.PUBLIC
