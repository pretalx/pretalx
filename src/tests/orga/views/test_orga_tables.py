# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json

import pytest
from django_scopes import scope

from pretalx.event.models import Event
from pretalx.submission.models import Submission, SubmissionType


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


@pytest.mark.django_db
def test_table_preferences_save_ordering(orga_client, event, orga_user):
    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "ordering": ["-title", "code"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        saved_ordering = prefs.get("tables.SubmissionTable.ordering")
        assert saved_ordering == ["-title", "code"]


@pytest.mark.django_db
def test_table_preferences_save_columns_and_ordering(orga_client, event, orga_user):
    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "columns": ["indicator", "title", "state"],
                "ordering": ["title"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200

    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        assert prefs.get("tables.SubmissionTable.columns") == [
            "indicator",
            "title",
            "state",
        ]
        assert prefs.get("tables.SubmissionTable.ordering") == ["title"]


@pytest.mark.django_db
def test_table_preferences_clear_ordering_with_empty_list(
    orga_client, event, orga_user
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.ordering", ["-title"], commit=True)

    url = event.orga_urls.base + "preferences/"
    response = orga_client.post(
        url,
        data=json.dumps(
            {
                "table_name": "SubmissionTable",
                "ordering": [],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        assert prefs.get("tables.SubmissionTable.ordering") is None


@pytest.mark.django_db
def test_submission_list_with_saved_ordering(orga_client, event, orga_user, submission):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.ordering", ["-title"], commit=True)

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
def test_submission_list_with_invalid_ordering_column(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.ordering",
            ["nonexistent_column", "title"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    assert submission.title in response.text


@pytest.mark.django_db
def test_submission_list_column_click_preserves_secondary_sort(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.ordering", ["title", "code"], commit=True)

    response = orga_client.get(
        event.orga_urls.submissions + "?sort=-state", follow=True
    )
    assert response.status_code == 200

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        ordering = prefs.get("tables.SubmissionTable.ordering")
        assert ordering == ["-state", "code"]


@pytest.mark.django_db
def test_submission_list_column_click_removes_duplicate_from_secondary(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.ordering", ["title", "code"], commit=True)

    response = orga_client.get(event.orga_urls.submissions + "?sort=code", follow=True)
    assert response.status_code == 200

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        ordering = prefs.get("tables.SubmissionTable.ordering")
        assert ordering == ["code"]


@pytest.mark.django_db
def test_submission_list_toggle_primary_preserves_secondary(
    orga_client, event, orga_user, submission
):
    with scope(event=event):
        prefs = orga_user.get_event_preferences(event)
        prefs.set("tables.SubmissionTable.ordering", ["title", "code"], commit=True)

    # Click title to reverse it (toggle direction)
    response = orga_client.get(
        event.orga_urls.submissions + "?sort=-title", follow=True
    )
    assert response.status_code == 200

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        ordering = prefs.get("tables.SubmissionTable.ordering")
        assert ordering == ["-title", "code"]

    # Click title again to toggle back
    response = orga_client.get(event.orga_urls.submissions + "?sort=title", follow=True)
    assert response.status_code == 200

    with scope(event=event):
        orga_user.event_preferences_cache.clear()
        prefs.refresh_from_db()
        ordering = prefs.get("tables.SubmissionTable.ordering")
        assert ordering == ["title", "code"]


@pytest.mark.django_db
def test_multicolumn_sorting_with_function_column(orga_client, event, orga_user):
    """Test that multi-column sorting works correctly when one column uses FunctionOrderMixin.

    The SubmissionTable's 'submission_type' column uses SortableColumn with
    order_by=Lower(Translate("submission_type__name")), which means it uses
    FunctionOrderMixin. This test verifies that multi-column sorting works
    when mixing function-based and regular columns.
    """
    with scope(event=event):
        type_a = SubmissionType.objects.create(event=event, name="AAA Type")
        type_z = SubmissionType.objects.create(event=event, name="ZZZ Type")
        Submission.objects.create(
            title="Alpha Talk",
            event=event,
            submission_type=type_a,
            content_locale="en",
        )
        Submission.objects.create(
            title="Beta Session",
            event=event,
            submission_type=type_z,
            content_locale="en",
        )
        Submission.objects.create(
            title="Gamma Presentation",
            event=event,
            submission_type=type_a,
            content_locale="en",
        )
        Submission.objects.create(
            title="Delta Demo",
            event=event,
            submission_type=type_z,
            content_locale="en",
        )
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.ordering",
            ["submission_type", "title"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    content = response.text

    pos_alpha = content.find("Alpha Talk")
    pos_gamma = content.find("Gamma Presentation")
    pos_beta = content.find("Beta Session")
    pos_delta = content.find("Delta Demo")

    # All submissions should appear
    assert pos_alpha > 0, "Alpha Talk not found in response"
    assert pos_gamma > 0, "Gamma Presentation not found in response"
    assert pos_beta > 0, "Beta Session not found in response"
    assert pos_delta > 0, "Delta Demo not found in response"

    # AAA Type submissions should come before ZZZ Type submissions
    assert pos_alpha < pos_beta, "AAA Type submissions should appear before ZZZ Type"
    assert pos_alpha < pos_delta, "AAA Type submissions should appear before ZZZ Type"
    assert pos_gamma < pos_beta, "AAA Type submissions should appear before ZZZ Type"
    assert pos_gamma < pos_delta, "AAA Type submissions should appear before ZZZ Type"

    # Within same type, alphabetical by title
    assert pos_alpha < pos_gamma, "Alpha should appear before Gamma (same type)"
    assert pos_beta < pos_delta, "Beta should appear before Delta (same type)"


@pytest.mark.django_db
def test_multicolumn_sorting_function_column_descending(orga_client, event, orga_user):
    with scope(event=event):
        type_a = SubmissionType.objects.create(event=event, name="AAA Type")
        type_z = SubmissionType.objects.create(event=event, name="ZZZ Type")

        Submission.objects.create(
            title="Alpha Talk",
            event=event,
            submission_type=type_a,
            content_locale="en",
        )
        Submission.objects.create(
            title="Beta Session",
            event=event,
            submission_type=type_z,
            content_locale="en",
        )
        prefs = orga_user.get_event_preferences(event)
        prefs.set(
            "tables.SubmissionTable.ordering",
            ["-submission_type", "title"],
            commit=True,
        )

    response = orga_client.get(event.orga_urls.submissions, follow=True)
    assert response.status_code == 200
    content = response.text

    pos_alpha = content.find("Alpha Talk")
    pos_beta = content.find("Beta Session")
    assert (
        pos_beta < pos_alpha
    ), "ZZZ Type should appear before AAA Type with -submission_type"
