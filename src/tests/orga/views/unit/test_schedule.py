# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils import translation

from pretalx.orga.views.schedule import (
    QuickScheduleView,
    RoomView,
    RoomVisibilityView,
    ScheduleExportView,
    ScheduleView,
    TalkUpdate,
    serialize_break,
    serialize_slot,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("locale", "expected"), (("en", "en"), ("de", "de_DE"), ("ja-jp", "ja_jp"))
)
def test_schedule_view_get_context_data_gettext_language(event, locale, expected):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleView, request)

    with translation.override(locale):
        context = view.get_context_data()

    assert context["gettext_language"] == expected


def test_schedule_export_view_exporters_excludes_speaker_group(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportView, request)

    exporters = view.exporters()

    assert exporters
    assert {exporter.group for exporter in exporters} == {"submission"}


def test_serialize_break(event):
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = event.datetime_from + dt.timedelta(minutes=30)
    placed = TalkSlotFactory(
        submission=None,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=end,
        is_visible=True,
    )
    unplaced = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=None, is_visible=True
    )

    assert serialize_break(placed) == {
        "id": placed.pk,
        "title": "",
        "description": "",
        "room": room.pk,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration": 30,
        "updated": placed.updated.isoformat(),
        "slot_type": placed.slot_type,
    }
    assert serialize_slot(placed) == serialize_break(placed)
    assert serialize_break(unplaced) == {
        "id": unplaced.pk,
        "title": "",
        "description": "",
        "room": None,
        "start": None,
        "end": None,
        "duration": unplaced.duration,
        "updated": unplaced.updated.isoformat(),
        "slot_type": unplaced.slot_type,
    }


def test_serialize_slot_with_submission(talk_slot):
    submission = talk_slot.submission

    assert serialize_slot(talk_slot, warnings=["Room conflict"]) == {
        "id": talk_slot.pk,
        "title": str(submission.title),
        "speakers": [
            {"name": speaker.get_display_name()}
            for speaker in submission.sorted_speakers
        ],
        "submission_type": str(submission.submission_type.name),
        "track": None,
        "state": submission.state,
        "description": str(submission.description),
        "abstract": str(submission.abstract),
        "notes": submission.notes,
        "duration": submission.get_duration(),
        "content_locale": submission.content_locale,
        "do_not_record": False,
        "room": talk_slot.room.pk,
        "start": talk_slot.local_start.isoformat(),
        "end": talk_slot.local_end.isoformat(),
        "url": submission.orga_urls.base,
        "warnings": ["Room conflict"],
        "updated": talk_slot.updated.isoformat(),
        "slot_type": talk_slot.slot_type,
    }
    assert serialize_slot(talk_slot)["warnings"] == []


def test_serialize_slot_with_track_speaker_and_flags(event):
    track = TrackFactory(event=event)
    speaker = SpeakerFactory(event=event, name="Test Speaker")
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        track=track,
        do_not_record=True,
        content_locale="de",
    )
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    result = serialize_slot(slot)

    assert result["track"] == {"name": str(track.name), "color": track.color}
    assert result["speakers"] == [{"name": "Test Speaker"}]
    assert result["do_not_record"] is True
    assert result["content_locale"] == "de"


def test_talk_update_get_object(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)

    assert make_view(TalkUpdate, request, pk=talk_slot.pk).get_object() == talk_slot
    assert make_view(TalkUpdate, request, pk=999999).get_object() is None


def test_quick_schedule_view_get_object_case_insensitive(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    code = talk_slot.submission.code

    assert make_view(QuickScheduleView, request, code=code).get_object() == talk_slot
    assert (
        make_view(QuickScheduleView, request, code=code.lower()).get_object()
        == talk_slot
    )


def test_room_view_get_queryset(event):
    used = TalkSlotFactory(submission__event=event).room
    hidden = RoomFactory(event=event, hidden=True)
    RoomFactory()
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "list"

    result = view.get_queryset()

    assert set(result) == {used, hidden}
    assert result.get(pk=used.pk).has_slots is True
    assert result.get(pk=used.pk).has_scheduled_slots is True
    assert result.get(pk=hidden.pk).has_slots is False


def test_room_visibility_view_requires_perform_action(event):
    room = RoomFactory(event=event)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomVisibilityView, request, pk=room.pk)

    with pytest.raises(NotImplementedError):
        view.perform_action()
