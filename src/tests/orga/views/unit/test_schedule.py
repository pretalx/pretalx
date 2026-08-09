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

    for exporter in exporters:
        assert exporter.group != "speaker"


def test_serialize_break_with_room(event):
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = event.datetime_from + dt.timedelta(minutes=30)
    slot = TalkSlotFactory(
        submission=None,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=end,
        is_visible=True,
    )

    result = serialize_break(slot)

    assert result["id"] == slot.pk
    assert result["room"] == room.pk
    assert result["start"] == start.isoformat()
    assert result["end"] == end.isoformat()
    assert result["duration"] == slot.duration
    assert result["updated"] == slot.updated.isoformat()


def test_serialize_break_without_room(event):
    slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=None, is_visible=True
    )

    result = serialize_break(slot)

    assert result["id"] == slot.pk
    assert result["room"] is None
    assert result["start"] is None
    assert result["end"] is None


def test_serialize_slot_with_submission(talk_slot):
    result = serialize_slot(talk_slot)

    assert result["id"] == talk_slot.pk
    assert result["title"] == str(talk_slot.submission.title)
    assert result["state"] == talk_slot.submission.state
    assert result["room"] == talk_slot.room.pk
    assert result["submission_type"] == str(talk_slot.submission.submission_type.name)
    assert result["url"] == talk_slot.submission.orga_urls.base
    assert result["abstract"] == str(talk_slot.submission.abstract)
    assert result["description"] == str(talk_slot.submission.description)
    assert result["warnings"] == []


def test_serialize_slot_with_submission_and_track(event):
    track = TrackFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, track=track
    )
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    result = serialize_slot(slot)

    assert result["track"]["name"] == str(track.name)
    assert result["track"]["color"] == track.color


def test_serialize_slot_without_track(talk_slot):
    result = serialize_slot(talk_slot)

    assert result["track"] is None


def test_serialize_slot_with_warnings(talk_slot):
    warnings = ["Speaker is unavailable", "Room conflict"]

    result = serialize_slot(talk_slot, warnings=warnings)

    assert result["warnings"] == warnings


def test_serialize_slot_without_warnings(talk_slot):
    result = serialize_slot(talk_slot)

    assert result["warnings"] == []


def test_serialize_slot_break_without_submission(event):
    room = RoomFactory(event=event)
    slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=room, is_visible=True
    )

    result = serialize_slot(slot)

    assert result["id"] == slot.pk
    assert result["room"] == room.pk
    assert "speakers" not in result
    assert "state" not in result


def test_talk_update_get_object_returns_slot(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TalkUpdate, request, pk=talk_slot.pk)

    result = view.get_object()

    assert result == talk_slot


def test_talk_update_get_object_returns_none_for_missing_slot(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TalkUpdate, request, pk=999999)

    result = view.get_object()

    assert result is None


def test_quick_schedule_view_get_object(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code)

    result = view.get_object()

    assert result == talk_slot


def test_quick_schedule_view_get_object_case_insensitive(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code.lower())

    result = view.get_object()

    assert result == talk_slot


def test_room_view_get_queryset(event):
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event, hidden=True)
    other_event_room = RoomFactory()  # different event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "list"

    result = set(view.get_queryset())

    assert result == {room1, room2}
    assert other_event_room not in result


def test_room_view_get_queryset_annotates_usage(event):
    room = TalkSlotFactory(submission__event=event).room
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "list"

    annotated = view.get_queryset().get(pk=room.pk)

    assert annotated.has_slots is True
    assert annotated.has_scheduled_slots is True


def test_room_visibility_view_requires_perform_action(event):
    room = RoomFactory(event=event)
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomVisibilityView, request, pk=room.pk)

    with pytest.raises(NotImplementedError):
        view.perform_action()


def test_serialize_slot_speakers_list(event):
    speaker = SpeakerFactory(event=event, name="Test Speaker")
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    result = serialize_slot(slot)

    assert len(result["speakers"]) == 1
    assert result["speakers"][0]["name"] == speaker.get_display_name()


def test_serialize_slot_do_not_record_flag(event):
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, do_not_record=True
    )
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    result = serialize_slot(slot)

    assert result["do_not_record"] is True


def test_serialize_slot_content_locale(event):
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, content_locale="de"
    )
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    result = serialize_slot(slot)

    assert result["content_locale"] == "de"
