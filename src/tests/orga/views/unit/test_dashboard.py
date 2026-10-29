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
    AvailabilityFactory,
    EventFactory,
    OrganiserFactory,
    QueuedMailFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _event_list_view(event, user, query=None):
    request = make_request(event, user=user)
    if query is not None:
        request.GET = request.GET.copy()
        request.GET["q"] = query
    return make_view(DashboardEventListView, request)


def test_event_list_view_queryset(event):
    EventFactory()
    speaker = SpeakerFactory(event=event)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    draft.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submitted.speakers.add(speaker)
    user = make_orga_user(event)

    view = _event_list_view(event, user)

    assert list(view.base_queryset) == [event]
    assert [(e.pk, e.submission_count) for e in view.queryset] == [(event.pk, 1)]
    assert list(_event_list_view(event, user, event.slug).queryset) == [event]
    assert list(_event_list_view(event, user, "nonexistent-slug-xyz").queryset) == []


def test_organiser_event_list_view_base_queryset_returns_organiser_events(event):
    EventFactory()  # other organiser's event, should be excluded
    user = make_orga_user(event)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(DashboardOrganiserEventListView, request)

    qs = view.base_queryset

    assert list(qs) == [event]


def test_organiser_list_view_organisers_admin_sees_all_and_filters():
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    searching = make_request(None, user=admin_user)
    searching.GET = searching.GET.copy()
    searching.GET["q"] = org1.slug

    assert {
        o.pk for o in make_view(DashboardOrganiserListView, request).organisers()
    } == {org1.pk, org2.pk}
    assert [
        o.slug for o in make_view(DashboardOrganiserListView, searching).organisers()
    ] == [org1.slug]


def test_organiser_list_view_organisers_non_admin_sees_own():
    org1 = OrganiserFactory()
    OrganiserFactory()  # second organiser the user should not see
    EventFactory(organiser=org1)
    user = UserFactory()
    team = TeamFactory(
        organiser=org1, can_change_organiser_settings=True, all_events=True
    )
    team.members.add(user)
    request = make_request(None, user=user)
    view = make_view(DashboardOrganiserListView, request)

    result = view.organisers()

    assert list(result) == [org1]
    assert result[0].event_count == 1
    assert result[0].team_count == 1


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


def _dashboard_view(event, user=None):
    user = user or make_orga_user(event)
    request = make_request(event, user=user)
    request.event = event
    return make_view(EventDashboardView, request)


def _tile_texts(tiles):
    return [str(tile.get("small", "")) for tile in tiles]


def test_event_dashboard_view_get_cfp_tiles():
    open_event = EventFactory(cfp__deadline=now() + dt.timedelta(days=10))
    SubmissionFactory(event=open_event, state=SubmissionStates.DRAFT)
    closed_event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    view = _dashboard_view(open_event)

    with_permission = _tile_texts(
        view.get_cfp_tiles(now(), can_change_submissions=True)
    )
    without_permission = _tile_texts(
        view.get_cfp_tiles(now(), can_change_submissions=False)
    )

    assert [text for text in with_permission if "until the CfP ends" in text]
    assert [text for text in with_permission if "unsubmitted proposal draft" in text]
    assert [text for text in without_permission if "until the CfP ends" in text]
    assert not [
        text for text in without_permission if "unsubmitted proposal draft" in text
    ]
    assert _dashboard_view(closed_event).get_cfp_tiles(now()) == []


def test_event_dashboard_view_get_review_tiles(event):
    assert _dashboard_view(event).get_review_tiles() == []

    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)

    tiles = _dashboard_view(event).get_review_tiles()

    review_tile = [t for t in tiles if str(t.get("small", "")) == "review"]
    assert len(review_tile) == 1
    assert review_tile[0]["large"] == 1
    assert review_tile[0]["url"] == event.orga_urls.reviews
    assert review_tile[0]["legend"][0]["count"] == 0


def test_event_dashboard_view_attention_items_show_the_outbox(event):
    view = _dashboard_view(event)
    assert view.get_attention_items(True, {"pending": 0, "accepted": 0}) == []

    QueuedMailFactory(event=event)
    items = view.get_attention_items(False, {"pending": 0, "accepted": 0})

    assert len(items) == 1
    assert items[0]["count"] == 1
    assert items[0]["url"] == event.orga_urls.outbox


def test_event_dashboard_view_attention_items_hide_the_outbox_without_permission(event):
    QueuedMailFactory(event=event)
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        all_events=True,
        can_change_submissions=False,
    )
    team.members.add(user)
    view = _dashboard_view(event, user)

    items = view.get_attention_items(False, {"pending": 0, "accepted": 0})

    assert items == []


def test_event_dashboard_view_attention_items_warn_about_access_code_only_cfp(event):
    event.submission_types.update(requires_access_code=True)
    view = _dashboard_view(event)

    items = view.get_attention_items(True, {"pending": 0, "accepted": 0})

    assert len(items) == 1
    assert items[0]["url"] == event.cfp.urls.types
    assert items[0]["warning"] is True


def test_event_dashboard_view_attention_items_warn_about_access_code_only_tracks():
    event = EventFactory(cfp__fields={"track": {"visibility": "required"}})
    TrackFactory(event=event, requires_access_code=True)
    view = _dashboard_view(event)

    items = view.get_attention_items(True, {"pending": 0, "accepted": 0})

    assert len(items) == 1
    assert items[0]["url"] == event.cfp.urls.tracks
    assert items[0]["warning"] is True


def test_event_dashboard_view_reviews_missing_only_for_reviewers(event):
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, is_reviewer=True, all_events=True)
    team.members.add(reviewer)

    assert _dashboard_view(event, reviewer).reviews_missing == 1
    assert _dashboard_view(event).reviews_missing == 0


def test_event_dashboard_view_get_plugin_tiles(event, register_signal_handler):
    tile = {"large": "Plugin!", "small": "test tile", "priority": 50}
    tile_list = [
        {"large": "A", "small": "first", "priority": 10},
        {"large": "B", "small": "second", "priority": 20},
    ]
    register_signal_handler(dashboard_tile, lambda signal, sender, **kwargs: tile)
    register_signal_handler(dashboard_tile, lambda signal, sender, **kwargs: tile_list)
    view = _dashboard_view(event)

    tiles = view.get_plugin_tiles()

    assert tile in tiles
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
    view = _dashboard_view(event, user)

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
    availability = AvailabilityFactory(event=event)
    log = ActivityLogFactory(
        event=event,
        person=UserFactory(),
        content_object=availability,
        action_type="pretalx.event.update",
    )

    def handler(signal, sender, activitylog, **kwargs):
        return '<a href="/plugin/">Custom object</a>'

    register_signal_handler(activitylog_object_link, handler)

    entry = activitylog_entry(log, hide_object_models=(Event, CfP))

    assert entry["object_url"] == ""
    assert entry["object_html"] == '<a href="/plugin/">Custom object</a>'
