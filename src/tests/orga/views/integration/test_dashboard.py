import datetime as dt

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.models.log import ActivityLog
from pretalx.submission.models import SubmissionStates
from tests.factories import (
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

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_start_redirect_view_anonymous_redirects_to_login(client):
    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


@pytest.mark.django_db
def test_start_redirect_view_single_orga_event_redirects_to_event(client, event):
    """User with exactly one orga event and no speaker events goes to that event."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.orga_urls.base


@pytest.mark.django_db
def test_start_redirect_view_single_speaker_event_redirects_to_submissions(
    client, event
):
    """User with exactly one speaker event and no orga events goes to submissions."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == event.urls.user_submissions


@pytest.mark.django_db
def test_start_redirect_view_multiple_events_redirects_to_list(client, event):
    """User with multiple events goes to the event list."""
    with scopes_disabled():
        EventFactory(organiser=event.organiser)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


@pytest.mark.django_db
def test_start_redirect_view_both_roles_redirects_to_list(client, event):
    """User who is both orga and speaker goes to the event list."""
    with scopes_disabled():
        user = make_orga_user(event)
        speaker = SpeakerFactory(event=event, user=user)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(reverse("orga:start.redirect"))

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


@pytest.mark.django_db
def test_event_list_view_orga_user_sees_own_event(client, event):
    """Organiser sees their events on the event list page."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert event.name in content


@pytest.mark.django_db
def test_event_list_view_orga_user_does_not_see_other_events(client, event):
    """Organiser does not see events they have no access to."""
    with scopes_disabled():
        other_event = EventFactory()
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(other_event.name) not in content


@pytest.mark.django_db
def test_event_list_view_anonymous_redirects_to_login(client):
    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


@pytest.mark.django_db
def test_event_list_view_admin_sees_all_events(client):
    """Administrators see all events."""
    with scopes_disabled():
        event1 = EventFactory()
        event2 = EventFactory()
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event1.name) in content
    assert str(event2.name) in content


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_list_view_shows_speaker_events(client, event):
    """The event list shows events where the user is a speaker."""
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


@pytest.mark.django_db
def test_event_list_view_search_filters_events(client, event):
    """?q= parameter filters events by name/slug."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(reverse("orga:event.list") + f"?q={event.slug}")

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.name) in content


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_view_query_count(
    client, event, item_count, django_assert_num_queries
):
    admin_user = UserFactory(is_administrator=True)
    with scopes_disabled():
        for _ in range(item_count - 1):
            EventFactory()
    client.force_login(admin_user)

    with django_assert_num_queries(5):
        response = client.get(reverse("orga:event.list"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_organiser_list_view_admin_sees_all_organisers(client):
    """Administrators see all organisers."""
    with scopes_disabled():
        org1 = OrganiserFactory()
        org2 = OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(org1.name) in content
    assert str(org2.name) in content


@pytest.mark.django_db
def test_organiser_list_view_orga_user_sees_own_organiser(client, event):
    """Orga user with organiser settings permission sees their organiser."""
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.organiser.name) in content


@pytest.mark.django_db
def test_organiser_list_view_orga_user_without_settings_perm_gets_404(client, event):
    """Orga user without can_change_organiser_settings gets 404."""
    user = make_orga_user(event, can_change_organiser_settings=False)
    client.force_login(user)

    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 404


@pytest.mark.django_db
def test_organiser_list_view_anonymous_redirects_to_login(client):
    response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 302
    assert "/orga/login/" in response.url


@pytest.mark.django_db
def test_organiser_list_view_search_filters(client):
    """?q= parameter filters organisers by slug/name."""
    with scopes_disabled():
        org1 = OrganiserFactory()
        OrganiserFactory()  # second organiser that should be excluded by search
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    response = client.get(reverse("orga:organiser.list") + f"?q={org1.slug}")

    assert response.status_code == 200
    context_orgs = response.context["organisers"]
    assert [o.slug for o in context_orgs] == [org1.slug]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_list_view_query_count(client, item_count, django_assert_num_queries):
    with scopes_disabled():
        for _ in range(item_count):
            OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    client.force_login(admin_user)

    with django_assert_num_queries(6):
        response = client.get(reverse("orga:organiser.list"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_organiser_event_list_view_shows_organiser_events(client, event):
    """Organiser dashboard shows events under that organiser."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert str(event.name) in content


@pytest.mark.django_db
def test_organiser_event_list_view_does_not_show_other_organiser_events(client, event):
    """Organiser dashboard does not include events from other organisers."""
    with scopes_disabled():
        other_event = EventFactory()
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert str(other_event.name) not in content


@pytest.mark.django_db
def test_organiser_event_list_view_unauthorized_user_gets_404(client, event):
    """User without organiser access gets 404."""
    user = UserFactory()
    client.force_login(user)

    response = client.get(
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug})
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_organiser_event_list_view_anonymous_redirects(client, event):
    response = client.get(
        reverse("orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug})
    )

    assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_event_list_view_query_count(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event)
    with scopes_disabled():
        for _ in range(item_count - 1):
            extra_event = EventFactory(organiser=event.organiser)
            team = user.teams.first()
            team.limit_events.add(extra_event)
    client.force_login(user)

    with django_assert_num_queries(7):
        response = client.get(
            reverse(
                "orga:organiser.dashboard", kwargs={"organiser": event.organiser.slug}
            )
        )

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_dashboard_view_orga_user_sees_dashboard(client, event):
    """Organiser can access the event dashboard."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    assert "timeline" in response.context
    assert "tiles" in response.context


@pytest.mark.django_db
def test_event_dashboard_view_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.base)

    assert response.status_code == 302


@pytest.mark.django_db
def test_event_dashboard_view_non_orga_user_gets_404(client, event):
    """User without any event permission gets 404."""
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_dashboard_view_tiles_sorted_by_priority(client, event):
    """Dashboard tiles are sorted by priority."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    priorities = [t.get("priority") or 100 for t in tiles]
    assert priorities == sorted(priorities)


@pytest.mark.django_db
def test_event_dashboard_view_shows_timeline(client, event):
    """Dashboard includes a timeline with event stages."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert "timeline" in response.context
    assert len(response.context["timeline"]) > 0


@pytest.mark.django_db
def test_event_dashboard_view_with_submissions(client, event):
    """Dashboard shows proposal count when there are submissions."""
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


@pytest.mark.django_db
def test_event_dashboard_view_with_accepted_submissions(client, event):
    """Dashboard shows session count when there are accepted submissions."""
    with scopes_disabled():
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    session_tiles = [t for t in tiles if "session" in str(t.get("small", "")).lower()]
    assert len(session_tiles) == 1


@pytest.mark.django_db
def test_event_dashboard_view_with_published_schedule(client, published_talk_slot):
    """Dashboard shows the current schedule version when a schedule is published."""
    event = published_talk_slot.submission.event
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    schedule_tiles = [t for t in tiles if "current schedule" in str(t.get("small", ""))]
    assert len(schedule_tiles) == 1
    assert schedule_tiles[0]["large"] == "v1"


@pytest.mark.django_db
def test_event_dashboard_view_with_pending_state_submissions(client, event):
    """Dashboard shows pending state changes tile."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.pending_state = SubmissionStates.ACCEPTED
        submission.save()
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    tiles = response.context["tiles"]
    pending_tiles = [t for t in tiles if "pending changes" in str(t.get("small", ""))]
    assert len(pending_tiles) == 1
    assert pending_tiles[0]["large"] == 1


@pytest.mark.django_db
def test_event_dashboard_view_with_speakers(client, event):
    """Dashboard shows speaker count when there are accepted talks with speakers."""
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "day_offset",
    (
        pytest.param(-3, id="past"),
        pytest.param(0, id="current"),
        pytest.param(3, id="future"),
    ),
)
def test_event_dashboard_view_different_event_dates(client, day_offset):
    """Dashboard renders for past, current, and future events."""
    today = now().date()
    with scopes_disabled():
        event = EventFactory(
            date_from=today + dt.timedelta(days=day_offset),
            date_to=today + dt.timedelta(days=day_offset + 2),
        )
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    assert "tiles" in response.context


@pytest.mark.django_db
def test_event_dashboard_view_future_event_shows_days_until(client):
    """Future event shows 'days until event start' tile."""
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


@pytest.mark.django_db
def test_event_dashboard_view_past_event_shows_days_since(client):
    """Past event shows 'days since event end' tile."""
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_dashboard_view_shows_sent_email_count(client, event):
    """Dashboard always shows a sent email count tile."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    tiles = response.context["tiles"]
    email_tiles = [t for t in tiles if "sent email" in str(t.get("small", "")).lower()]
    assert len(email_tiles) == 1
    assert email_tiles[0]["large"] == 0


@pytest.mark.django_db
def test_event_dashboard_view_shows_history(client, event):
    """Dashboard shows recent activity log entries."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        user = make_orga_user(event)
        ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=submission,
            action_type="pretalx.submission.create",
        )
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200
    history = response.context["history"]
    assert len(history) == 1


@pytest.mark.django_db
def test_event_dashboard_view_reviewer_only_access(client, event):
    """A reviewer-only user can access the event dashboard."""
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
        team.members.add(user)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_dashboard_view_reviewer_does_not_see_speaker_names(client, event):
    """A reviewer without settings access does not see speaker names on the dashboard.

    The history section (which shows person names from activity logs) is gated
    behind can_change_settings, so reviewer-only users never see it."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        ActivityLog.objects.create(
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


@pytest.mark.django_db
def test_event_dashboard_view_with_reviews(client, event):
    """Dashboard shows review count tile when reviews exist."""
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


@pytest.mark.django_db
def test_event_dashboard_view_go_to_target_cfp_before_review_done(client, event):
    """go_to_target is 'cfp' when review phase is not done."""
    user = make_orga_user(event)
    client.force_login(user)

    response = client.get(event.orga_urls.base)

    assert response.context["go_to_target"] == "cfp"


@pytest.mark.django_db
def test_event_dashboard_view_query_count(client, event, django_assert_num_queries):
    """Guard against query regressions on the event dashboard with realistic data."""
    with scopes_disabled():
        event.cfp.deadline = now()
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        ReviewFactory(submission=submission)
    user = make_orga_user(event)
    client.force_login(user)

    with django_assert_num_queries(24):
        response = client.get(event.orga_urls.base)

    assert response.status_code == 200
