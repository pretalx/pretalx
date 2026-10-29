# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404
from django_scopes import scope

from pretalx.api.views.schedule import ScheduleViewSet, TalkSlotViewSet
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import ScheduleFactory, SubmissionFactory, TalkSlotFactory
from tests.utils import make_api_request, make_view, refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_viewset_get_serializer_context_only_visible_slots_for_public(
    event, orga_user
):
    views = {
        "orga": make_view(
            ScheduleViewSet, make_api_request(event=event, user=orga_user)
        ),
        "anonymous": make_view(ScheduleViewSet, make_api_request(event=event)),
        "no_event": make_view(ScheduleViewSet, make_api_request()),
    }
    for view in views.values():
        view.format_kwarg = None

    assert views["orga"].get_serializer_context()["only_visible_slots"] is False
    assert views["anonymous"].get_serializer_context()["only_visible_slots"] is True
    assert not views["no_event"].get_serializer_context()["only_visible_slots"]


def test_schedule_viewset_get_queryset_public_sees_only_current(event, orga_user):
    orga_view = make_view(
        ScheduleViewSet, make_api_request(event=event, user=orga_user)
    )
    anonymous_view = make_view(ScheduleViewSet, make_api_request(event=event))
    no_event_view = make_view(ScheduleViewSet, make_api_request())

    assert list(no_event_view.get_queryset()) == []
    assert list(anonymous_view.get_queryset()) == []
    assert list(orga_view.get_queryset()) == [event.wip_schedule]

    schedule = ScheduleFactory(event=event, version="v1")
    # current_schedule is cached
    event = refresh(event)
    orga_view = make_view(
        ScheduleViewSet, make_api_request(event=event, user=orga_user)
    )
    anonymous_view = make_view(ScheduleViewSet, make_api_request(event=event))

    assert list(anonymous_view.get_queryset()) == [schedule]
    assert set(orga_view.get_queryset()) == {event.wip_schedule, schedule}


def test_schedule_viewset_get_object_by_alias(event, orga_user):
    request = make_api_request(event=event, user=orga_user)

    def get_object(alias):
        view = make_view(ScheduleViewSet, request, pk=alias)
        view.action = "retrieve"
        view.detail = True
        return view.get_object()

    assert get_object("wip") == event.wip_schedule
    with pytest.raises(Http404):
        get_object("latest")

    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    event.refresh_from_db()

    assert get_object("latest") == event.current_schedule
    assert event.current_schedule.version == "v1"


def test_talk_slot_viewset_is_orga(event, orga_user):
    orga_view = make_view(
        TalkSlotViewSet, make_api_request(event=event, user=orga_user)
    )
    anonymous_view = make_view(TalkSlotViewSet, make_api_request(event=event))

    assert orga_view.is_orga is True
    assert anonymous_view.is_orga is False


def test_talk_slot_viewset_get_queryset_public_sees_visible_current_slots(
    event, orga_user
):
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    visible = TalkSlotFactory(submission=confirmed, is_visible=True)
    unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=unscheduled, is_visible=True, start=None)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    event.refresh_from_db()

    def slots(user=None, action="retrieve"):
        view = make_view(TalkSlotViewSet, make_api_request(event=event, user=user))
        view.action = action
        return list(view.get_queryset().order_by("pk"))

    orga_slots = slots(user=orga_user)
    assert len(orga_slots) == 4
    assert {slot.schedule_id for slot in orga_slots} == {
        event.wip_schedule.pk,
        event.current_schedule.pk,
    }
    assert slots() == [visible]
    assert slots(action="list") == [visible]
    assert visible.schedule_id == event.current_schedule.pk
    no_event_view = make_view(TalkSlotViewSet, make_api_request())
    assert list(no_event_view.get_queryset()) == []
