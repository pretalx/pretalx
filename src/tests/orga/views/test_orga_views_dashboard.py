# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.models.log import ActivityLog
from pretalx.event.models import Event, Team
from pretalx.person.models import SpeakerProfile


@pytest.mark.parametrize("test_user", ("orga", "speaker", "superuser", "None"))
@pytest.mark.parametrize("query", ("", "?q=e"))
@pytest.mark.django_db
def test_dashboard_event_list(
    orga_user, orga_client, speaker, event, other_event, test_user, slot, query
):
    if test_user == "speaker":
        orga_client.force_login(speaker)
    elif test_user == "None":
        orga_client.logout()
    elif test_user == "superuser":
        orga_user.is_administrator = True
        orga_user.save()

    response = orga_client.get(reverse("orga:event.list") + query, follow=True)

    if test_user == "speaker":
        assert response.status_code == 200
        assert event.slug not in response.text
    elif test_user == "orga":
        assert response.status_code == 200
        assert event.slug in response.text
        assert other_event.slug not in response.text
    elif test_user == "superuser":
        assert response.status_code == 200
        assert event.slug in response.text, response.text
        assert other_event.slug in response.text, response.text
    else:
        current_url = response.redirect_chain[-1][0]
        assert "login" in current_url


@pytest.mark.parametrize(
    "test_user", ("orga", "speaker", "superuser", "reviewer", "None")
)
@pytest.mark.parametrize("query", ("", "?q=e"))
@pytest.mark.django_db
def test_event_dashboard(
    orga_user, orga_client, review_user, speaker, event, test_user, slot, query
):
    ActivityLog.objects.create(
        event=event,
        person=speaker,
        content_object=slot.submission,
        action_type="pretalx.submission.create",
    )
    if test_user == "speaker":
        orga_client.force_login(speaker)
    elif test_user == "None":
        orga_client.logout()
    elif test_user == "superuser":
        orga_user.is_administrator = True
        orga_user.save()
    elif test_user == "reviewer":
        with scope(event=event):
            event.active_review_phase.can_see_speaker_names = False
            event.active_review_phase.save()
        orga_client.force_login(review_user)

    response = orga_client.get(event.orga_urls.base + query, follow=True)

    if test_user == "speaker":
        assert response.status_code == 404
        assert event.slug not in response.text
    elif test_user == "orga":
        assert response.status_code == 200
        assert event.slug in response.text
        assert speaker.name in response.text
    elif test_user == "superuser":
        assert response.status_code == 200
        assert event.slug in response.text, response.text
        assert speaker.name in response.text
    elif test_user == "reviewer":
        assert not review_user.has_perm("person.orga_list_speakerprofile", event)
        assert response.status_code == 200
        assert event.slug in response.text, response.text
        assert speaker.name not in response.text
    else:
        current_url = response.redirect_chain[-1][0]
        assert "login" in current_url


@pytest.mark.parametrize("test_user", ("orga", "speaker", "superuser", "None"))
@pytest.mark.django_db
def test_dashboard_organiser_list(
    orga_user, orga_client, speaker, event, other_event, test_user
):
    if test_user == "speaker":
        orga_client.force_login(speaker)
    elif test_user == "None":
        orga_client.logout()
    elif test_user == "superuser":
        orga_user.is_administrator = True
        orga_user.save()

    response = orga_client.get(reverse("orga:organiser.list"), follow=True)

    if test_user == "speaker":
        assert response.status_code == 404, response.status_code
    elif test_user == "orga":
        assert event.organiser.name in response.text
        assert other_event.organiser.name not in response.text
    elif test_user == "superuser":
        assert event.organiser.name in response.text, response.text
        assert other_event.organiser.name in response.text, response.text
    else:
        current_url = response.redirect_chain[-1][0]
        assert "login" in current_url


@pytest.mark.django_db
def test_event_dashboard_with_talks(
    event, orga_client, review_user, review, slot, django_assert_num_queries
):
    with scope(event=event):
        event.cfp.deadline = now()
        event.save()
    expected_queries = 34
    with django_assert_num_queries(expected_queries):
        response = orga_client.get(event.orga_urls.base)
    assert response.status_code == 200


@pytest.mark.django_db
def test_event_dashboard_with_accepted(
    event, orga_client, review_user, review, slot, accepted_submission
):
    with scope(event=event):
        event.cfp.deadline = now()
        event.save()
    response = orga_client.get(event.orga_urls.base)
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_organiser_list_num_queries(
    orga_client, orga_user, event, other_event, django_assert_num_queries, item_count
):
    orga_user.is_administrator = True
    orga_user.save()

    if item_count != 2:
        other_event.organiser.shred()

    with django_assert_num_queries(6):
        response = orga_client.get(reverse("orga:organiser.list"))
    assert response.status_code == 200
    assert event.organiser.name in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_event_list_num_queries(
    orga_client, orga_user, event, other_event, django_assert_num_queries, item_count
):
    if item_count == 2:
        orga_user.is_administrator = True
        orga_user.save()

    # Admin path (item_count=2) skips team-based filtering, using fewer queries
    expected_queries = 5 if item_count == 2 else 6
    with django_assert_num_queries(expected_queries):
        response = orga_client.get(reverse("orga:event.list"))
    assert response.status_code == 200
    assert event.slug in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_organiser_event_list_num_queries(
    orga_client, orga_user, event, django_assert_num_queries, item_count
):
    if item_count == 2:
        with scope(event=event):
            second_event = Event.objects.create(
                name="Second Event",
                slug="second",
                email="orga@orga.org",
                date_from=dt.date.today(),
                date_to=dt.date.today(),
                organiser=event.organiser,
            )
            for team in event.organiser.teams.all():
                team.limit_events.add(second_event)

    with django_assert_num_queries(8):
        response = orga_client.get(
            reverse(
                "orga:organiser.dashboard",
                kwargs={"organiser": event.organiser.slug},
            )
        )
    assert response.status_code == 200
    assert event.slug in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_organiser_speakers_num_queries(
    orga_client,
    event,
    slot,
    other_slot,
    speaker_profile,
    other_speaker,
    django_assert_num_queries,
    item_count,
):
    with scope(event=event):
        if item_count != 2:
            profile = SpeakerProfile.objects.get(user=other_speaker, event=event)
            profile.user = None
            profile.save()
            profile.delete()

    with django_assert_num_queries(13):
        response = orga_client.get(
            reverse(
                "orga:organiser.speakers",
                kwargs={"organiser": event.organiser.slug},
            )
        )
    assert response.status_code == 200
    assert speaker_profile.get_display_name() in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_teams_list_num_queries(
    orga_client, event, django_assert_num_queries, item_count
):
    if item_count == 2:
        with scope(event=event):
            Team.objects.create(
                name="Extra Team", organiser=event.organiser, is_reviewer=True
            )

    with django_assert_num_queries(12):
        response = orga_client.get(event.organiser.orga_urls.teams)
    assert response.status_code == 200
    assert "Organisers" in response.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start_diff", "end_diff"),
    (
        (0, 0),
        (-3, -3),
        (3, 3),
    ),
)
def test_event_dashboard_different_times(event, orga_client, start_diff, end_diff):
    with scope(event=event):
        today = now().date()
        event.date_from = today + dt.timedelta(days=start_diff)
        event.date_end = today + dt.timedelta(days=end_diff)
        event.save()
    response = orga_client.get(event.orga_urls.base)
    assert response.status_code == 200
