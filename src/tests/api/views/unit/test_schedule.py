# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404
from django_scopes import scope

from pretalx.api.views.schedule import ScheduleViewSet, TalkSlotViewSet
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("is_orga", "expected_only_visible"),
    ((True, False), (False, True)),
    ids=["orga_sees_all", "non_orga_only_visible"],
)
def test_schedule_viewset_get_serializer_context_only_visible_slots(
    event, is_orga, expected_only_visible
):
    if is_orga:
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(user)
    else:
        user = None

    request = make_api_request(event=event, user=user)
    view = make_view(ScheduleViewSet, request)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert context["only_visible_slots"] is expected_only_visible


def test_schedule_viewset_get_serializer_context_no_event():
    request = make_api_request()
    view = make_view(ScheduleViewSet, request)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert not context["only_visible_slots"]


def test_schedule_viewset_get_queryset_no_event():
    request = make_api_request()
    view = make_view(ScheduleViewSet, request)

    assert list(view.get_queryset()) == []


def test_schedule_viewset_get_queryset_orga_sees_all(event):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    ScheduleFactory(event=event, version="v1")
    total = event.schedules.count()
    assert total >= 2  # WIP + v1

    request = make_api_request(event=event, user=user)
    view = make_view(ScheduleViewSet, request)

    assert view.get_queryset().count() == total


def test_schedule_viewset_get_queryset_anonymous_sees_only_current(event):
    schedule = ScheduleFactory(event=event, version="v1")
    event.current_schedule = schedule
    event.save()

    request = make_api_request(event=event)
    view = make_view(ScheduleViewSet, request)

    qs = view.get_queryset()
    assert list(qs) == [event.current_schedule]


def test_schedule_viewset_get_queryset_anonymous_empty_without_current(event):
    request = make_api_request(event=event)
    view = make_view(ScheduleViewSet, request)

    assert list(view.get_queryset()) == []


def test_schedule_viewset_get_object_wip(event):
    """Looking up 'wip' returns the WIP schedule."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)

    request = make_api_request(event=event, user=user)
    view = make_view(ScheduleViewSet, request, pk="wip")
    view.action = "retrieve"
    view.detail = True

    obj = view.get_object()
    assert obj == event.wip_schedule
    assert obj.version is None


def test_schedule_viewset_get_object_latest(event):
    """Looking up 'latest' returns the current released schedule."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)

    request = make_api_request(event=event, user=user)
    view = make_view(ScheduleViewSet, request, pk="latest")
    view.action = "retrieve"
    view.detail = True

    obj = view.get_object()
    assert obj == event.current_schedule
    assert obj.version == "v1"


def test_schedule_viewset_get_object_latest_404_without_current(event):
    """Looking up 'latest' raises Http404 when no schedule is released."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)

    request = make_api_request(event=event, user=user)
    view = make_view(ScheduleViewSet, request, pk="latest")
    view.action = "retrieve"
    view.detail = True

    with pytest.raises(Http404):
        view.get_object()


@pytest.mark.parametrize(
    ("has_perm", "expected"),
    ((True, True), (False, False)),
    ids=["orga_user", "anonymous_user"],
)
def test_talk_slot_viewset_is_orga(event, has_perm, expected):
    if has_perm:
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(user)
    else:
        user = None

    request = make_api_request(event=event, user=user)
    view = make_view(TalkSlotViewSet, request)

    assert view.is_orga is expected


def test_talk_slot_viewset_get_queryset_no_event():
    request = make_api_request()
    view = make_view(TalkSlotViewSet, request)

    assert list(view.get_queryset()) == []


def test_talk_slot_viewset_get_queryset_orga_sees_all(event):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    team.members.add(user)
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    visible = TalkSlotFactory(submission=sub, is_visible=True)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    invisible = TalkSlotFactory(submission=sub2, is_visible=False)

    request = make_api_request(event=event, user=user)
    view = make_view(TalkSlotViewSet, request)
    view.action = "retrieve"

    qs = view.get_queryset()
    pks = set(qs.values_list("pk", flat=True))
    assert visible.pk in pks
    assert invisible.pk in pks


def test_talk_slot_viewset_get_queryset_anonymous_filters_visible(event):
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=sub, is_visible=True)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=sub2, is_visible=False)
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)

    request = make_api_request(event=event)
    view = make_view(TalkSlotViewSet, request)
    view.action = "retrieve"

    qs = view.get_queryset()
    # Only visible slots on released schedules
    for slot in qs:
        assert slot.is_visible is True
        assert slot.schedule.version is not None


def test_talk_slot_viewset_get_queryset_list_defaults_to_current_schedule(event):
    sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=sub, is_visible=True)
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)

    request = make_api_request(event=event)
    view = make_view(TalkSlotViewSet, request)
    view.action = "list"

    qs = view.get_queryset()
    for slot in qs:
        assert slot.schedule == event.current_schedule
