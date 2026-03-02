# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import RequestFactory

from pretalx.api.filters.schedule import TalkSlotFilter
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit

rf = RequestFactory()


@pytest.mark.django_db
def test_talk_slot_filter_init_with_event_populates_querysets():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    room = RoomFactory(event=event)

    request = rf.get("/")
    request.event = event
    f = TalkSlotFilter(request=request)

    wip = event.wip_schedule
    assert list(f.filters["submission"].queryset) == [sub]
    assert list(f.filters["room"].queryset) == [room]
    assert list(f.filters["schedule"].queryset) == [wip]
    assert list(f.filters["schedule_version"].queryset) == [wip]


@pytest.mark.django_db
def test_talk_slot_filter_filters_by_submission_code(event):
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot1 = TalkSlotFactory(submission=sub1)
    TalkSlotFactory(submission=sub2)

    request = rf.get("/")
    request.event = event
    fs = TalkSlotFilter(
        data={"submission": sub1.code},
        queryset=TalkSlot.objects.filter(schedule=event.wip_schedule),
        request=request,
    )

    assert list(fs.qs) == [slot1]


@pytest.mark.django_db
def test_talk_slot_filter_filters_by_room(event):
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot1 = TalkSlotFactory(submission=sub1, room=room1)
    TalkSlotFactory(submission=sub2, room=room2)

    request = rf.get("/")
    request.event = event
    fs = TalkSlotFilter(
        data={"room": str(room1.pk)},
        queryset=TalkSlot.objects.filter(schedule=event.wip_schedule),
        request=request,
    )

    assert list(fs.qs) == [slot1]


@pytest.mark.django_db
def test_talk_slot_filter_filters_by_is_visible(event):
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    slot_visible = TalkSlotFactory(submission=sub1, is_visible=True)
    TalkSlotFactory(submission=sub2, is_visible=False)

    fs = TalkSlotFilter(
        data={"is_visible": "true"},
        queryset=TalkSlot.objects.filter(schedule=event.wip_schedule),
    )

    assert list(fs.qs) == [slot_visible]
