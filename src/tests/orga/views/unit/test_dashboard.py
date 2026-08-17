# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.common.log import activitylog_entry
from pretalx.common.signals import activitylog_object_link
from pretalx.event.models import Event
from pretalx.orga.signals import dashboard_tile
from pretalx.orga.views.dashboard import (
    DashboardEventListView,
    DashboardOrganiserEventListView,
    DashboardOrganiserListView,
    EventDashboardView,
)
from pretalx.submission.models import CfP, SubmissionStates
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    OrganiserFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_list_view_queryset_excludes_drafts(event):
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
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.GET = request.GET.copy()
    request.GET["q"] = event.slug
    view = make_view(DashboardEventListView, request)

    qs = view.queryset

    assert list(qs) == [event]


def test_event_list_view_queryset_search_excludes_nonmatching(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.GET = request.GET.copy()
    request.GET["q"] = "nonexistent-slug-xyz"
    view = make_view(DashboardEventListView, request)

    qs = view.queryset

    assert list(qs) == []


def test_event_list_view_base_queryset_uses_user_permissions(event):
    EventFactory()  # other event the user should not see
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(DashboardEventListView, request)

    qs = view.base_queryset

    assert list(qs) == [event]


def test_organiser_event_list_view_base_queryset_returns_organiser_events(event):
    EventFactory()  # other organiser's event, should be excluded
    user = make_orga_user(event)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(DashboardOrganiserEventListView, request)

    qs = view.base_queryset

    assert list(qs) == [event]


def test_organiser_list_view_organisers_admin_sees_all():
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert {o.pk for o in result} == {org1.pk, org2.pk}


def test_organiser_list_view_organisers_non_admin_sees_own():
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
    org1 = OrganiserFactory()
    OrganiserFactory()  # second organiser that should be excluded by search
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    request.GET = request.GET.copy()
    request.GET["q"] = org1.slug
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert [o.slug for o in result] == [org1.slug]


def test_event_dashboard_view_get_cfp_tiles_deadline_in_future():
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
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_cfp_tiles(now())

    assert not tiles


def test_event_dashboard_view_get_review_tiles_with_reviews(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles()

    review_tile = [t for t in tiles if str(t.get("small", "")) == "review"]
    assert len(review_tile) == 1
    assert review_tile[0]["large"] == 1
    assert review_tile[0]["url"] == event.orga_urls.reviews
    assert review_tile[0]["legend"][0]["count"] == 0


def test_event_dashboard_view_get_review_tiles_no_reviews(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    tiles = view.get_review_tiles()

    assert tiles == []


def test_event_dashboard_view_reviews_missing_for_reviewer(event):
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
    team.members.add(user)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    assert view.reviews_missing == 1


def test_event_dashboard_view_reviews_missing_for_non_reviewer(event):
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    view = make_view(EventDashboardView, request)

    assert view.reviews_missing == 0


def test_event_dashboard_view_get_plugin_tiles_with_signal(
    event, register_signal_handler
):
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


def test_event_dashboard_view_activity_groups(event):
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

    groups = view.activity_groups()

    assert len(groups) == 1
    assert len(groups[0]["entries"]) == 1
    entry = groups[0]["entries"][0]
    assert entry["log"].person == user
    assert entry["object_url"] == submission.orga_urls.base
    assert entry["object_text"] == submission.title


def test_event_dashboard_view_activity_entry_hides_event_object(event):
    user = UserFactory()
    log = ActivityLogFactory(
        event=event,
        person=user,
        content_object=event,
        action_type="pretalx.event.update",
    )
    entry = activitylog_entry(log, hide_object_models=(Event, CfP))

    assert entry["object_url"] == ""
    assert entry["object_text"] == ""


def test_event_dashboard_view_activity_entry_plugin_object(
    event, register_signal_handler
):
    track = TrackFactory(event=event)
    log = ActivityLogFactory(
        event=event,
        person=UserFactory(),
        content_object=track,
        action_type="pretalx.event.update",
    )

    def handler(signal, sender, activitylog, **kwargs):
        return f'<a href="/plugin/">{activitylog.content_object.name}</a>'

    register_signal_handler(activitylog_object_link, handler)

    entry = activitylog_entry(log, hide_object_models=(Event, CfP))

    assert entry["object_url"] == ""
    assert entry["object_html"] == f'<a href="/plugin/">{track.name}</a>'
