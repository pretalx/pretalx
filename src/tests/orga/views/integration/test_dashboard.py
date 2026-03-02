# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

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
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_start_redirect_view_anonymous_redirects_to_login(client):
    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


def test_start_redirect_view_single_orga_event_redirects_to_event(client, event):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.orga_urls.base


def test_start_redirect_view_single_speaker_event_redirects_to_submissions(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.urls.user_submissions


def test_start_redirect_view_multiple_events_redirects_to_list(client, event):
    with scopes_disabled():
        EventFactory(organiser=event.organiser)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


def test_start_redirect_view_both_roles_redirects_to_list(client, event):
    with scopes_disabled():
        user = make_orga_user(event)
        speaker = SpeakerFactory(event=event, user=user)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


def test_event_list_view_orga_user_sees_own_event(client, event):
    with scopes_disabled():
        other_event = EventFactory()
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert event.name in content
    assert str(other_event.name) not in content


def test_event_list_view_anonymous_redirects_to_login(client):
    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_view_admin_sees_all_events(
    client, item_count, django_assert_num_queries
):
    """Administrators see all events with constant query count."""
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


def test_event_list_view_separates_current_and_past_events(client, event):
    """Current events (date_to >= today) and past events are in separate lists."""
    with scopes_disabled():
        past_event = EventFactory(
            organiser=event.organiser,
            date_from=now().date() - dt.timedelta(days=30),
            date_to=now().date() - dt.timedelta(days=28),
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    assert list(response.context["current_orga_events"]) == [event]
    assert list(response.context["past_orga_events"]) == [past_event]


def test_event_list_view_shows_speaker_events(client, event):
    user = make_orga_user(event)
    with scopes_disabled():
        speaker_event = EventFactory()
        speaker = SpeakerFactory(event=speaker_event, user=user)
        submission = SubmissionFactory(event=speaker_event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    assert list(response.context["speaker_events"]) == [speaker_event]


@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_list_view_admin_sees_all_organisers(
    client, item_count, django_assert_num_queries
):
    """Administrators see all organisers with constant query count."""
    with scopes_disabled():
        organisers = OrganiserFactory.create_batch(item_count)
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    with django_assert_num_queries(6):
        response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    for org in organisers:
        assert str(org.name) in content


def test_organiser_list_view_orga_user_sees_own_organiser(client, event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.organiser.name) in content


def test_organiser_list_view_orga_user_without_settings_perm_gets_404(client, event):
    user = make_orga_user(event, can_change_organiser_settings=False)
    client.force_login(user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_event_list_view_shows_organiser_events(
    client, event, item_count, django_assert_num_queries
):
    """Organiser dashboard shows events under that organiser, excludes others."""
    user = make_orga_user(event)
    with scopes_disabled():
        for _ in range(item_count - 1):
            extra_event = EventFactory(organiser=event.organiser)
            team = user.teams.first()
            team.limit_events.add(extra_event)
        other_event = EventFactory()
    client.force_login(user)

    with django_assert_num_queries(7):
        response = client.get(
            reverse(
                "orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug}
            )
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.name) in content
    assert str(other_event.name) not in content


def test_organiser_event_list_view_unauthorized_user_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug})
    )

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_dashboard_view_orga_user_sees_dashboard(
    client, item_count, django_assert_num_queries
):
    """Organiser sees dashboard with tiles, timeline, and constant query count."""
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

    with django_assert_num_queries(24):
        response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    assert "timeline" in response.context
    tiles = response.context["tiles"]
    assert len(tiles) > 0
    priorities = [t.get("priority") or 100 for t in tiles]
    assert priorities == sorted(priorities)
    email_tiles = [t for t in tiles if "sent email" in str(t.get("small", "")).lower()]
    assert len(email_tiles) == 1


def test_event_dashboard_view_go_to_target_cfp_before_review_done(client, event):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.context["go_to_target"] == "cfp"


def test_event_dashboard_view_non_orga_user_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 404


def test_event_dashboard_view_with_submissions(client, event):
    with scopes_disabled():
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    proposal_tiles = [t for t in tiles if "proposal" in str(t.get("small", "")).lower()]
    assert len(proposal_tiles) == 1
    assert proposal_tiles[0]["large"] == 1


def test_event_dashboard_view_with_accepted_submissions(client, event):
    with scopes_disabled():
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    session_tiles = [t for t in tiles if "session" in str(t.get("small", "")).lower()]
    assert len(session_tiles) == 1


def test_event_dashboard_view_with_published_schedule(client, published_talk_slot):
    event = published_talk_slot.submission.event
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    schedule_tiles = [t for t in tiles if "current schedule" in str(t.get("small", ""))]
    assert len(schedule_tiles) == 1
    assert schedule_tiles[0]["large"] == "v1"


def test_event_dashboard_view_with_pending_state_submissions(client, event):
    with scopes_disabled():
        SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    pending_tiles = [t for t in tiles if "pending changes" in str(t.get("small", ""))]
    assert len(pending_tiles) == 1
    assert pending_tiles[0]["large"] == 1


def test_event_dashboard_view_with_speakers(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        slot.schedule.freeze("v1", notify_speakers=False)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    speaker_tiles = [t for t in tiles if "speaker" in str(t.get("small", "")).lower()]
    assert len(speaker_tiles) == 1
    assert speaker_tiles[0]["large"] == 1


def test_event_dashboard_view_future_event_shows_days_until(client):
    today = now().date()
    with scopes_disabled():
        event = EventFactory(
            date_from=today + dt.timedelta(days=10),
            date_to=today + dt.timedelta(days=12),
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    countdown_tiles = [
        t for t in tiles if "until event start" in str(t.get("small", ""))
    ]
    assert len(countdown_tiles) == 1
    assert countdown_tiles[0]["large"] == 10


def test_event_dashboard_view_past_event_shows_days_since(client):
    today = now().date()
    with scopes_disabled():
        event = EventFactory(
            date_from=today - dt.timedelta(days=10),
            date_to=today - dt.timedelta(days=8),
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    since_tiles = [t for t in tiles if "since event end" in str(t.get("small", ""))]
    assert len(since_tiles) == 1


def test_event_dashboard_view_multi_day_running_event_shows_day_number(client):
    """Multi-day running event shows 'Day N of M days' tile."""
    today = now().date()
    with scopes_disabled():
        event = EventFactory(
            date_from=today - dt.timedelta(days=1), date_to=today + dt.timedelta(days=1)
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    day_tiles = [
        t
        for t in tiles
        if "of" in str(t.get("small", "")) and "days" in str(t.get("small", ""))
    ]
    assert len(day_tiles) == 1


def test_event_dashboard_view_single_day_running_event_no_day_tile(client):
    """A single-day event running today does not show a 'Day N of M' tile."""
    today = now().date()
    with scopes_disabled():
        event = EventFactory(date_from=today, date_to=today)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    day_tiles = [
        t
        for t in tiles
        if "of" in str(t.get("small", "")) and "days" in str(t.get("small", ""))
    ]
    assert len(day_tiles) == 0


def test_event_dashboard_view_reviewer_only_access(client, event):
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
        team.members.add(user)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200


def test_event_dashboard_view_reviewer_does_not_see_speaker_names(client, event):
    """A reviewer without settings access does not see speaker names on the dashboard.

    The history section (which shows person names from activity logs) is gated
    behind can_change_settings, so reviewer-only users never see it."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
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
    assert speaker.user.name not in response.content.decode()


def test_event_dashboard_view_with_reviews(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        ReviewFactory(submission=submission)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    review_tiles = [t for t in tiles if str(t.get("small", "")) == "Reviews"]
    assert len(review_tiles) == 1
    assert review_tiles[0]["large"] == 1
