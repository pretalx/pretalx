import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled

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


def test_talk_slot_filter_without_event_has_empty_querysets():
    with scopes_disabled():
        f = TalkSlotFilter()
    assert f.filters["submission"].queryset.count() == 0
    assert f.filters["schedule"].queryset.count() == 0
    assert f.filters["schedule_version"].queryset.count() == 0
    assert f.filters["room"].queryset.count() == 0


@pytest.mark.django_db
def test_talk_slot_filter_init_with_event_populates_querysets():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        room = RoomFactory(event=event)

        request = rf.get("/")
        request.event = event
        f = TalkSlotFilter(request=request)

    with scopes_disabled():
        wip = event.wip_schedule
    assert list(f.filters["submission"].queryset) == [sub]
    assert list(f.filters["room"].queryset) == [room]
    assert list(f.filters["schedule"].queryset) == [wip]
    assert list(f.filters["schedule_version"].queryset) == [wip]


@pytest.mark.django_db
def test_talk_slot_filter_filters_by_submission_code(event):
    with scopes_disabled():
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
    with scopes_disabled():
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
    with scopes_disabled():
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        slot_visible = TalkSlotFactory(submission=sub1, is_visible=True)
        TalkSlotFactory(submission=sub2, is_visible=False)

        fs = TalkSlotFilter(
            data={"is_visible": "true"},
            queryset=TalkSlot.objects.filter(schedule=event.wip_schedule),
        )

    assert list(fs.qs) == [slot_visible]


def test_talk_slot_filter_speaker_queryset_not_populated_in_init():
    """The speaker filter queryset is never populated in __init__,
    it remains User.objects.none() regardless of event."""
    with scopes_disabled():
        f = TalkSlotFilter()
    assert f.filters["speaker"].queryset.count() == 0
