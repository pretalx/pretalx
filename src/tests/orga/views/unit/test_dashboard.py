# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.orga.signals import dashboard_tile
from pretalx.orga.views.dashboard import (
    DashboardEventListView,
    DashboardOrganiserEventListView,
    DashboardOrganiserListView,
    EventDashboardView,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    OrganiserFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_list_view_queryset_excludes_drafts(event):
    """The submission_count annotation excludes draft submissions."""
    speaker = SpeakerFactory(event=event)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    draft.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submitted.speakers.add(speaker)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(DashboardEventListView, request)

    qs = view.queryset
    annotated_event = [e for e in qs if e.pk == event.pk][0]

    assert annotated_event.submission_count == 1


def test_event_list_view_queryset_filters_by_search(event):
    """The queryset filters events by name or slug when ?q= is provided."""
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.GET = request.GET.copy()
    request.GET["q"] = event.slug
    view = make_view(DashboardEventListView, request)

    qs = view.queryset

    assert list(qs) == [event]


def test_event_list_view_queryset_search_excludes_nonmatching(event):
    """Search excludes events whose name and slug don't match."""
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.GET = request.GET.copy()
    request.GET["q"] = "nonexistent-slug-xyz"
    view = make_view(DashboardEventListView, request)

    qs = view.queryset

    assert list(qs) == []


def test_event_list_view_base_queryset_uses_user_permissions(event):
    """base_queryset returns only events the user has permissions for."""
    EventFactory()  # other event the user should not see
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(DashboardEventListView, request)

    qs = view.base_queryset

    assert list(qs) == [event]


def test_organiser_event_list_view_base_queryset_returns_organiser_events(event):
    """base_queryset returns all events under the request organiser."""
    EventFactory()  # other organiser's event, should be excluded
    user = make_orga_user(event)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(DashboardOrganiserEventListView, request)

    qs = view.base_queryset

    assert list(qs) == [event]


def test_organiser_list_view_organisers_admin_sees_all():
    """Administrators see all organisers."""
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert {o.pk for o in result} == {org1.pk, org2.pk}


def test_organiser_list_view_organisers_non_admin_sees_own():
    """Non-admin users see only organisers they have settings access to."""
    org1 = OrganiserFactory()
    OrganiserFactory()  # second organiser the user should not see
    user = UserFactory()
    team = TeamFactory(
        organiser=org1, can_change_organiser_settings=True, all_events=True
    )
    team.members.add(user)
    request = make_request(None, user=user)
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert list(result) == [org1]


@pytest.mark.parametrize(
    ("query_attr", "expected"),
    (
        pytest.param("slug", True, id="matches_slug"),
        pytest.param("name", True, id="matches_name"),
        pytest.param(None, False, id="rejects_nonmatching"),
    ),
)
def test_organiser_list_view_filter_organiser(query_attr, expected):
    org = OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    view = make_view(DashboardOrganiserListView, request)

    query = str(getattr(org, query_attr)) if query_attr else "nonexistent-xyz-999"
    assert view.filter_organiser(org, query) == expected


def test_organiser_list_view_organisers_with_search_query():
    """Search via ?q= filters the organiser list."""
    org1 = OrganiserFactory()
    OrganiserFactory()  # second organiser that should be excluded by search
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    request.GET = request.GET.copy()
    request.GET["q"] = org1.slug
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert [o.slug for o in result] == [org1.slug]


def test_event_dashboard_view_get_cfp_tiles_open_cfp():
    """When CfP is open, includes a 'Go to CfP' tile."""
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=30))
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now())

    urls = [t.get("url") for t in tiles]
    assert event.cfp.urls.public in urls


def test_event_dashboard_view_get_cfp_tiles_deadline_in_future():
    """When deadline is in the future, includes a 'time until CfP ends' tile."""
    future = now() + dt.timedelta(days=10)
    event = EventFactory(cfp__deadline=future)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now())

    has_until_tile = any("until the CfP ends" in str(t.get("small", "")) for t in tiles)
    assert has_until_tile


def test_event_dashboard_view_get_cfp_tiles_drafts_with_permission():
    """Draft proposals tile shown when user can change submissions and CfP is open."""
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=10))
    SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now(), can_change_submissions=True)

    has_drafts_tile = any(
        "unsubmitted proposal draft" in str(t.get("small", "")) for t in tiles
    )
    assert has_drafts_tile


def test_event_dashboard_view_get_cfp_tiles_drafts_without_permission():
    """Draft proposals tile not shown without can_change_submissions."""
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=10))
    SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now(), can_change_submissions=False)

    has_drafts_tile = any(
        "unsubmitted proposal draft" in str(t.get("small", "")) for t in tiles
    )
    assert not has_drafts_tile


def test_event_dashboard_view_get_cfp_tiles_closed_cfp():
    """When CfP is closed (deadline in the past), no 'Go to CfP' tile."""
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now())

    assert not tiles


def test_event_dashboard_view_get_review_tiles_with_reviews(event):
    """Review tiles show review count and active reviewer count."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles(can_change_settings=False)

    review_tile = [t for t in tiles if str(t.get("small", "")) == "Reviews"]
    assert len(review_tile) == 1
    assert review_tile[0]["large"] == 1


def test_event_dashboard_view_get_review_tiles_no_reviews(event):
    """No review tiles when there are no reviews and user is not a reviewer."""
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles(can_change_settings=False)

    assert tiles == []


def test_event_dashboard_view_get_review_tiles_reviewer_with_missing_reviews(event):
    """Reviewer sees 'waiting for your review' tile when reviews are missing."""
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
    team.members.add(user)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles(can_change_settings=False)

    waiting_tiles = [
        t for t in tiles if "waiting for your review" in str(t.get("small", ""))
    ]
    assert len(waiting_tiles) == 1
    assert waiting_tiles[0]["large"] == 1


def test_event_dashboard_view_get_review_tiles_active_reviewers_url_with_settings_perm(
    event,
):
    """Active reviewers tile links to teams page when user can change settings."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles(can_change_settings=True)

    reviewer_tile = [t for t in tiles if str(t.get("small", "")) == "Active reviewers"]
    assert len(reviewer_tile) == 1
    assert reviewer_tile[0]["url"] == event.organiser.orga_urls.teams


def test_event_dashboard_view_get_review_tiles_active_reviewers_url_without_settings_perm(
    event,
):
    """Active reviewers tile has no link when user cannot change settings."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles(can_change_settings=False)

    reviewer_tile = [t for t in tiles if str(t.get("small", "")) == "Active reviewers"]
    assert len(reviewer_tile) == 1
    assert reviewer_tile[0]["url"] is None


def test_event_dashboard_view_get_plugin_tiles_with_signal(
    event, register_signal_handler
):
    """Plugin tiles are collected from the dashboard_tile signal."""
    tile_data = {"large": "Plugin!", "small": "test tile", "priority": 50}

    def handler(signal, sender, **kwargs):
        return tile_data

    register_signal_handler(dashboard_tile, handler)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_plugin_tiles()

    assert tile_data in tiles


def test_event_dashboard_view_get_plugin_tiles_list_response(
    event, register_signal_handler
):
    """Plugin tile signal handlers may return a list of tiles."""
    tile_list = [
        {"large": "A", "small": "first", "priority": 10},
        {"large": "B", "small": "second", "priority": 20},
    ]

    def handler(signal, sender, **kwargs):
        return tile_list

    register_signal_handler(dashboard_tile, handler)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_plugin_tiles()

    assert tile_list[0] in tiles
    assert tile_list[1] in tiles


def test_event_dashboard_view_history(event):
    """History returns recent activity logs for the event."""
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    ActivityLogFactory(
        event=event,
        person=user,
        content_object=submission,
        action_type="pretalx.submission.create",
    )
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    history = view.history()

    assert len(history) == 1
    assert history[0].event == event
