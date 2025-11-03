# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json

import pytest
from django_scopes import scope

from pretalx.event.models import Event


@pytest.mark.django_db
def test_table_preferences_save_columns(orga_client, event, orga_user):
    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "columns": ["indicator", "title", "code", "state"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        saved_columns = prefs.get("tables.SubmissionTable.columns")
        assert saved_columns == ["indicator", "title", "code", "state"]


@pytest.mark.django_db
def test_table_preferences_reset(orga_client, event, orga_user):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.columns", ["title", "code"], commit=True)

    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "reset": True,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        saved_columns = prefs.get("tables.SubmissionTable.columns")
        assert saved_columns is None


@pytest.mark.django_db
def test_table_preferences_invalid_table_name(orga_client, event):
    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps({"columns": ["title"]}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data


@pytest.mark.django_db
def test_table_preferences_invalid_json(orga_client, event):
    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data="not valid json",
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data


@pytest.mark.django_db
def test_table_preferences_requires_authentication(client, event):
    url = event.orga_urls.base + "preferences/"
    response = client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "columns": ["title"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in [302, 403]


@pytest.mark.django_db
def test_submission_list_with_saved_preferences(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "code", "state"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200

    assert submission.title in response.text
    assert submission.speakers.first().name not in response.text


@pytest.mark.django_db
def test_submission_list_with_nonexistent_column(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "nonexistent_column", "state"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
def test_submission_list_with_excluded_column(
    orga_client, event, orga_user, submission, review_user
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "speakers", "state"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text

    review_client = orga_client.__class__()
    review_client.force_login(review_user)

    with scope(event=event):
        submission.event.active_review_phase.can_see_speaker_names = False
        submission.event.active_review_phase.save()

        review_prefs = review_user.get_event_preferences(event)
        review_prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "speakers", "state"],
            commit=True,
        )

    response = review_client.get(
        event.orga_urls.submissions + "?state=submitted", follow=True
    )
    assert response.status_code == 200
    assert submission.speakers.first().name not in response.content.decode()


@pytest.mark.django_db
def test_submission_list_with_hidden_columns_shown(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "created", "state"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text
    assert submission.created.astimezone(event.tz).date().isoformat() in response.text


@pytest.mark.django_db
def test_event_copy_preserves_table_preferences(orga_client, event, orga_user):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.columns",
            ["indicator", "title", "code", "state"],
            commit=True,
        )
        prefs.set("tables.SpeakerTable.columns", ["name", "email"], commit=True)

    with scope(event=event):
        new_event = Event.objects.create(
            organiser=event.organiser,
            name="Copied Event",
            slug="copied-event",
            date_from=dt.date.today() + dt.timedelta(days=365),
            date_to=dt.date.today() + dt.timedelta(days=366),
            timezone="UTC",
        )
        new_event.copy_data_from(event)

    with scope(event=new_event):
        new_prefs = orga_user.get_event_preferences(new_event)
        submission_cols = new_prefs.get("tables.SubmissionTable.columns")
        speaker_cols = new_prefs.get("tables.SpeakerTable.columns")

        assert submission_cols == ["indicator", "title", "code", "state"]
        assert speaker_cols == ["name", "email"]
