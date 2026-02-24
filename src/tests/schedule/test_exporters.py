import datetime as dt
import json

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import ResolverMatch
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.schedule.exporters import (
    FavedICalExporter,
    FrabJsonExporter,
    FrabXCalExporter,
    FrabXmlExporter,
    ICalExporter,
    ScheduleData,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_schedule_data_metadata_with_schedule(event, schedule_with_talk):
    sd = ScheduleData(event=event, schedule=schedule_with_talk)

    metadata = sd.metadata

    assert "url" in metadata
    assert "base_url" in metadata


@pytest.mark.django_db
def test_schedule_data_data_returns_day_entries(event, schedule_with_talk):
    sd = ScheduleData(event=event, schedule=schedule_with_talk)

    with scope(event=event):
        data = list(sd.data)

    assert len(data) == event.duration
    day = data[0]
    assert day["index"] == 1
    assert "start" in day
    assert "end" in day
    assert "rooms" in day


@pytest.mark.django_db
def test_schedule_data_data_includes_visible_talks(event, schedule_with_talk):
    sd = ScheduleData(event=event, schedule=schedule_with_talk)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    assert len(rooms_with_talks) == 1
    room = rooms_with_talks[0]["rooms"][0]
    assert len(room["talks"]) == 1
    assert room["talks"][0].submission is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("with_accepted", "expected_count"),
    ((False, 0), (True, 1)),
    ids=["excluded_without_accepted", "included_with_accepted"],
)
def test_schedule_data_data_invisible_talk_visibility(
    event, with_accepted, expected_count
):
    """Non-visible talks are excluded unless with_accepted=True."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        slot = TalkSlotFactory(submission=submission, is_visible=False)

    sd = ScheduleData(event=event, schedule=slot.schedule, with_accepted=with_accepted)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    assert len(rooms_with_talks) == expected_count


@pytest.mark.django_db
@pytest.mark.parametrize(
    "slot_overrides",
    ({"start": None, "end": None}, {"room": None}),
    ids=["without_start", "without_room"],
)
def test_schedule_data_data_skips_incomplete_talk(event, slot_overrides):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        TalkSlotFactory(submission=submission, is_visible=True, **slot_overrides)
        schedule = event.wip_schedule

    sd = ScheduleData(event=event, schedule=schedule, with_accepted=True)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    assert rooms_with_talks == []


@pytest.mark.django_db
def test_schedule_data_data_rooms_sorted_by_position(event):
    with scopes_disabled():
        room_b = RoomFactory(event=event, name="Room B", position=2)
        room_a = RoomFactory(event=event, name="Room A", position=1)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        TalkSlotFactory(submission=sub1, room=room_b, is_visible=True)
        TalkSlotFactory(submission=sub2, room=room_a, is_visible=True)
        schedule = event.wip_schedule

    sd = ScheduleData(event=event, schedule=schedule, with_accepted=True)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    room_names = [str(r["name"]) for r in rooms_with_talks[0]["rooms"]]
    assert room_names == ["Room A", "Room B"]


@pytest.mark.django_db
def test_schedule_data_data_late_night_talk_assigned_to_previous_day(event):
    """A talk starting before 3am is assigned to the previous day."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        late_start = event.datetime_from + dt.timedelta(days=1, hours=2)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=late_start,
            end=late_start + dt.timedelta(hours=1),
        )
        schedule = event.wip_schedule

    sd = ScheduleData(event=event, schedule=schedule, with_accepted=True)

    with scope(event=event):
        data = list(sd.data)

    # The talk at 02:00 on day 2 should be assigned to day 1
    data = list(data)
    day1 = data[0]
    day2_rooms = [day for day in data[1:] if day["rooms"]]
    assert len(day1["rooms"]) == 1
    assert day2_rooms == []


@pytest.mark.django_db
def test_schedule_data_tracks_first_start_and_last_end(
    event, talk_slot, schedule_with_talk
):
    sd = ScheduleData(event=event, schedule=schedule_with_talk)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    day = rooms_with_talks[0]
    assert day["first_start"] == talk_slot.start
    assert day["last_end"] == talk_slot.local_end


@pytest.mark.django_db
def test_frab_xml_exporter_get_data(event, schedule_with_talk):
    exporter = FrabXmlExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = exporter.get_data()

    assert result.startswith("<?xml")
    assert "<schedule>" in result
    assert f"<acronym>{event.slug}</acronym>" in result


@pytest.mark.django_db
def test_frab_xcal_exporter_get_data(event, schedule_with_talk):
    exporter = FrabXCalExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = exporter.get_data()

    assert "vcalendar" in result.lower()
    assert "vevent" in result.lower()


@pytest.mark.django_db
def test_frab_json_exporter_class_attributes(event):
    exporter = FrabJsonExporter(event)
    assert exporter.verbose_name == "JSON (frab compatible)"
    assert exporter.public is True
    assert exporter.icon == "{ }"
    assert exporter.cors == "*"
    assert exporter.extension == "json"
    assert exporter.content_type == "application/json"
    assert exporter.identifier == "schedule.json"


@pytest.mark.django_db
def test_frab_json_exporter_get_data_returns_valid_json(event, schedule_with_talk):
    exporter = FrabJsonExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = exporter.get_data()

    parsed = json.loads(result)
    assert "$schema" in parsed
    assert "generator" in parsed
    assert parsed["generator"]["name"] == "pretalx"
    assert "schedule" in parsed


@pytest.mark.django_db
def test_frab_json_exporter_get_data_conference_structure(event, schedule_with_talk):
    exporter = FrabJsonExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = json.loads(exporter.get_data())

    conference = result["schedule"]["conference"]
    assert conference["acronym"] == event.slug
    assert conference["title"] == str(event.name)
    assert conference["start"] == event.date_from.strftime("%Y-%m-%d")
    assert conference["end"] == event.date_to.strftime("%Y-%m-%d")
    assert conference["time_zone_name"] == event.timezone
    assert "days" in conference
    assert "rooms" in conference
    assert "tracks" in conference


@pytest.mark.django_db
def test_frab_json_exporter_get_data_includes_talk(event, schedule_with_talk):
    exporter = FrabJsonExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = json.loads(exporter.get_data())

    days = result["schedule"]["conference"]["days"]
    all_talks = [
        talk
        for day in days
        for room_talks in day["rooms"].values()
        for talk in room_talks
    ]
    assert len(all_talks) == 1
    talk = all_talks[0]
    assert "title" in talk
    assert "code" in talk
    assert "persons" in talk
    assert "duration" in talk
    assert "room" in talk


@pytest.mark.django_db
def test_ical_exporter_class_attributes(event):
    exporter = ICalExporter(event)
    assert str(exporter.verbose_name) == "iCal (full event)"
    assert exporter.public is True
    assert exporter.show_public is False
    assert exporter.show_qrcode is True
    assert exporter.icon == "fa-calendar"
    assert exporter.cors == "*"
    assert exporter.extension == "ics"
    assert exporter.content_type == "text/calendar"
    assert exporter.identifier == "schedule.ics"


@pytest.mark.django_db
def test_ical_exporter_get_data(event, schedule_with_talk):
    exporter = ICalExporter(event, schedule=schedule_with_talk)

    with scope(event=event):
        result = exporter.get_data()

    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" in result
    assert "END:VCALENDAR" in result


@pytest.mark.django_db
def test_faved_ical_exporter_class_attributes(event):
    exporter = FavedICalExporter(event)
    assert str(exporter.verbose_name) == "iCal (your starred sessions)"
    assert exporter.show_qrcode is False
    assert exporter.icon == "fa-calendar"
    assert exporter.show_public is True
    assert exporter.cors == "*"
    assert exporter.extension == "ics"
    assert exporter.content_type == "text/calendar"
    assert exporter.identifier == "faved.ics"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("namespaces", "user_type", "expected"),
    (
        (["agenda"], "with_perm", True),
        (["orga"], "with_perm", False),
        (["agenda"], "anon", False),
        (["agenda"], "no_perm", False),
    ),
    ids=("all_conditions_met", "wrong_namespace", "unauthenticated", "no_permission"),
)
def test_faved_ical_exporter_is_public(rf, event, namespaces, user_type, expected):
    exporter = FavedICalExporter(event)
    request = rf.get("/")
    request.resolver_match = ResolverMatch(lambda: None, (), {}, namespaces=namespaces)
    request.event = event

    if user_type == "anon":
        request.user = AnonymousUser()
    elif user_type == "with_perm":
        user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        team.members.add(user)
        request.user = user
    else:
        request.user = UserFactory()

    assert exporter.is_public(request) is expected


@pytest.mark.django_db
def test_faved_ical_exporter_get_data_unauthenticated(rf, event):
    exporter = FavedICalExporter(event)
    request = rf.get("/")
    request.user = AnonymousUser()

    assert exporter.get_data(request=request) is None


@pytest.mark.django_db
def test_schedule_data_data_out_of_bounds_talk_skipped(event):
    """Talks whose date falls outside the event date range are skipped."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        # Schedule a talk a week before the event
        out_of_range_start = event.datetime_from - dt.timedelta(days=7)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=out_of_range_start,
            end=out_of_range_start + dt.timedelta(hours=1),
        )
        schedule = event.wip_schedule

    sd = ScheduleData(event=event, schedule=schedule, with_accepted=True)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    assert rooms_with_talks == []


@pytest.mark.django_db
def test_schedule_data_data_multiple_talks_same_room(event):
    """Multiple talks in the same room are grouped together."""
    with scopes_disabled():
        room = RoomFactory(event=event)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        start1 = event.datetime_from
        start2 = event.datetime_from + dt.timedelta(hours=2)
        TalkSlotFactory(
            submission=sub1,
            room=room,
            is_visible=True,
            start=start1,
            end=start1 + dt.timedelta(hours=1),
        )
        TalkSlotFactory(
            submission=sub2,
            room=room,
            is_visible=True,
            start=start2,
            end=start2 + dt.timedelta(hours=1),
        )
        schedule = event.wip_schedule

    sd = ScheduleData(event=event, schedule=schedule, with_accepted=True)

    with scope(event=event):
        data = list(sd.data)

    rooms_with_talks = [day for day in data if day["rooms"]]
    assert len(rooms_with_talks) == 1
    room_data = rooms_with_talks[0]["rooms"][0]
    assert len(room_data["talks"]) == 2


@pytest.mark.django_db
def test_faved_ical_exporter_get_data_authenticated(rf, event, schedule_with_talk):
    """get_data returns ical content for an authenticated user with a published schedule."""
    with scopes_disabled():
        user = UserFactory()
        schedule = schedule_with_talk
        schedule.version = "v1"
        schedule.published = now()
        schedule.save()
        event.current_schedule = schedule

    exporter = FavedICalExporter(event)
    request = rf.get("/")
    request.user = user
    request.event = event

    with scope(event=event):
        result = exporter.get_data(request=request)

    assert "BEGIN:VCALENDAR" in result
