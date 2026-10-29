# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.orga.signals import activate_event
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    OrganiserFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _tiles(response):
    return [(str(tile["small"]), tile["large"]) for tile in response.context["tiles"]]


def _attention_items(response):
    return [
        (item.get("count"), str(item.get("text", item.get("type"))))
        for item in response.context["attention_items"]
    ]


def test_dashboard_views_redirect_anonymous_to_login(client):
    for url in (reverse("orga:start.redirect"), reverse("orga:event.list")):
        response = client.get(url)
        assert response.status_code == 302, url
        assert response.url == f"/orga/login/?next={url}", url


def test_dashboard_views_deny_unrelated_user(client, event):
    client.force_login(make_orga_user(event, can_change_organiser_settings=False))

    assert client.get(reverse("orga:organiser.list")).status_code == 404

    client.force_login(UserFactory())

    for url in (
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug}),
        event.orga_urls.base,
    ):
        assert client.get(url).status_code == 404, url


def test_start_redirect_view_orga_user(client, event):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.orga_urls.base

    with scopes_disabled():
        EventFactory(organiser=event.organiser)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


def test_start_redirect_view_speaker(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.urls.user_submissions

    with scopes_disabled():
        make_orga_user(event).teams.get().members.add(speaker.user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


def test_event_list_view_groups_events_by_role_and_date(client, event):
    user = make_orga_user(event)
    with scopes_disabled():
        other_event = EventFactory(name="Unrelated Event")
        past_event = EventFactory(
            organiser=event.organiser,
            date_from=now().date() - dt.timedelta(days=30),
            date_to=now().date() - dt.timedelta(days=28),
        )
        speaker_event = EventFactory()
        speaker = SpeakerFactory(event=speaker_event, user=user)
        submission = SubmissionFactory(event=speaker_event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    assert list(response.context["current_orga_events"]) == [event]
    assert list(response.context["past_orga_events"]) == [past_event]
    assert list(response.context["speaker_events"]) == [speaker_event]
    content = response.content.decode()
    assert str(event.name) in content
    assert str(other_event.name) not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_view_admin_sees_all_events(
    client, item_count, django_assert_num_queries
):
    with scopes_disabled():
        events = EventFactory.create_batch(item_count)
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    with django_assert_num_queries(5):
        response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    content = response.content.decode()
    for event in events:
        assert str(event.name) in content


def test_event_list_view_offers_event_creation_only_with_an_organiser(client):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    assert "/orga/event/new/" not in response.content.decode()

    with scopes_disabled():
        event = EventFactory()

    response = client.get(reverse("orga:event.list"))

    assert "/orga/event/new/" in response.content.decode()

    client.force_login(make_orga_user(event, can_create_events=True))

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    assert "/orga/event/new/" in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_list_view_admin_sees_all_organisers(
    client, item_count, django_assert_num_queries
):
    with scopes_disabled():
        organisers = OrganiserFactory.create_batch(item_count)
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    with django_assert_num_queries(5):
        response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    for org in organisers:
        assert str(org.name) in content


def test_organiser_list_view_orga_user_sees_own_organiser(client, event):
    with scopes_disabled():
        other_organiser = OrganiserFactory(name="Unrelated Organiser")
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.organiser.name) in content
    assert str(other_organiser.name) not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_event_list_view_shows_organiser_events(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event)
    with scopes_disabled():
        for _ in range(item_count - 1):
            extra_event = EventFactory(organiser=event.organiser)
            team = user.teams.first()
            team.limit_events.add(extra_event)
        other_event = EventFactory()
    client.force_login(user)

    with django_assert_num_queries(5):
        response = client.get(
            reverse(
                "orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug}
            )
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.name) in content
    assert str(other_event.name) not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_dashboard_view_orga_user_sees_dashboard(
    client, item_count, django_assert_num_queries
):
    with scopes_disabled():
        event = EventFactory(cfp__deadline=now())
        submissions = SubmissionFactory.create_batch(
            item_count, event=event, state=SubmissionStates.SUBMITTED
        )
        for sub in submissions:
            speaker = SpeakerFactory(event=event)
            sub.speakers.add(speaker)
            ReviewFactory(submission=sub)
    user = make_orga_user(event)
    client.force_login(user)

    with django_assert_num_queries(21):
        response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    assert len(tiles) > 0
    priorities = [t.get("priority") or 100 for t in tiles]
    assert priorities == sorted(priorities)
    email_tiles = [t for t in tiles if "sent email" in str(t.get("small", "")).lower()]
    assert len(email_tiles) == 1


def test_event_dashboard_view_counts_submissions_sessions_speakers_and_reviews(
    client, event
):
    with scopes_disabled():
        pending = SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
        ReviewFactory(submission=pending)
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        confirmed.speakers.add(SpeakerFactory(event=event))
        slot = TalkSlotFactory(submission=confirmed, is_visible=True)
        freeze_schedule(slot.schedule, "v1", notify_speakers=False)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    assert _tiles(response) == [
        ("session", 1),
        ("speaker", 1),
        ("proposals", 3),
        ("review", 1),
        ("sent emails", 0),
    ]
    session_tile, _, proposal_tile, *_ = response.context["tiles"]
    assert [
        (legend["label"], legend["count"]) for legend in session_tile["legend"]
    ] == [("confirmed", 1), ("unconfirmed", 1)]
    assert [
        (legend["label"], legend["count"]) for legend in proposal_tile["legend"]
    ] == [("accepted", 2), ("rejected", 0)]
    assert _attention_items(response) == [
        (1, "submission has pending changes"),
        (1, "session is still unconfirmed"),
    ]


def test_event_dashboard_view_shows_event_date_progress(client, event):
    today = now().date()
    user = make_orga_user(event)
    client.force_login(user)

    event.date_from = today + dt.timedelta(days=10)
    event.date_to = today + dt.timedelta(days=12)
    event.save()
    response = client.get(event.orga_urls.base)

    assert _tiles(response) == [
        ("days until event start", 10),
        ("submitters", 0),
        ("sent emails", 0),
    ]
    assert "running_day" not in response.context

    event.date_from = today - dt.timedelta(days=10)
    event.date_to = today - dt.timedelta(days=8)
    event.save()
    response = client.get(event.orga_urls.base)

    assert _tiles(response) == [
        ("submitters", 0),
        ("days since event end", 8),
        ("sent emails", 0),
    ]
    assert "running_day" not in response.context

    event.date_from = today - dt.timedelta(days=1)
    event.date_to = today + dt.timedelta(days=1)
    event.save()
    response = client.get(event.orga_urls.base)

    assert _tiles(response) == [("submitters", 0), ("sent emails", 0)]
    assert response.context["running_day"] == 2
    assert response.context["running_day_total"] == 3

    event.date_from = today
    event.date_to = today
    event.save()
    response = client.get(event.orga_urls.base)

    assert _tiles(response) == [("submitters", 0), ("sent emails", 0)]
    assert "running_day" not in response.context


def test_event_dashboard_view_reviewer_sees_review_queue_without_speaker_names(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, name="Hidden Speaker Name")
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        ActivityLogFactory(
            event=event,
            person=speaker.user,
            content_object=submission,
            action_type="pretalx.submission.create",
        )
        reviewer = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
        team.members.add(reviewer)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    assert "Hidden Speaker Name" not in response.content.decode()
    assert _attention_items(response) == [(1, "proposal is waiting for your review")]
    assert response.context["attention_items"][0]["url"] == event.orga_urls.reviews


def trial_blocker(signal, sender, check, **kwargs):
    raise ValueError(f"Trial mode, [sign up here](/p/billing/). check={check}")


def test_event_dashboard_view_go_live_row_and_activation_blockers(
    client, event, register_signal_handler
):
    with scopes_disabled():
        event.is_public = False
        event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.context["attention_items"][0] == {"type": "live"}
    assert response.context["activation_blockers"] == []
    content = response.content.decode()
    assert "dialog-live" in content
    assert "Go live" in content

    register_signal_handler(activate_event, trial_blocker)
    response = client.get(event.orga_urls.base)

    content = response.content.decode()
    assert [str(blocker) for blocker in response.context["activation_blockers"]] == [
        "Trial mode, [sign up here](/p/billing/). check=True"
    ]
    assert content.count('href="/p/billing/"') == 2
    assert "Go live" not in content

    response = client.get(event.orga_urls.live)

    assert response.status_code == 302
    assert response.url == event.orga_urls.base

    with scopes_disabled():
        event.is_public = True
        event.save()
    response = client.get(event.orga_urls.base)

    assert response.context["activation_blockers"] == []
    assert response.context["attention_items"] == []

    with scopes_disabled():
        event.is_public = False
        event.save()
    client.force_login(make_orga_user(event, can_change_event_settings=False))
    response = client.get(event.orga_urls.base)

    assert response.context["activation_blockers"] == []
    assert response.context["attention_items"] == []


def test_event_dashboard_view_warns_about_access_code_only_cfp(client, event):
    with scopes_disabled():
        event.submission_types.update(requires_access_code=True)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    content = response.content.decode()
    assert "nobody can submit a proposal without an access code" in content
    assert event.cfp.urls.types in content

    with scopes_disabled():
        event.submission_types.update(requires_access_code=False)
        event.cfp.fields = {**event.cfp.fields, "track": {"visibility": "required"}}
        event.cfp.save()
        TrackFactory(event=event, requires_access_code=True)

    response = client.get(event.orga_urls.base)

    content = response.content.decode()
    assert "every track requires an access code" in content
    assert event.cfp.urls.tracks in content
