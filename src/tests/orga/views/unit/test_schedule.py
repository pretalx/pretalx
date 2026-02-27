import datetime as dt

import pytest
from django_scopes import scopes_disabled

from pretalx.orga.views.schedule import (
    QuickScheduleView,
    RoomView,
    ScheduleExportDownloadView,
    ScheduleExportView,
    ScheduleReleaseView,
    ScheduleView,
    TalkUpdate,
    serialize_break,
    serialize_slot,
)
from pretalx.schedule.models import Room
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_schedule_view_get_context_data_includes_gettext_language(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleView, request)

    with scopes_disabled():
        context = view.get_context_data()

    assert "gettext_language" in context
    assert isinstance(context["gettext_language"], str)


@pytest.mark.django_db
def test_schedule_export_view_get_form_kwargs_passes_event(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportView, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event


@pytest.mark.django_db
def test_schedule_export_view_exporters_excludes_speaker_group(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportView, request)

    with scopes_disabled():
        exporters = view.exporters()

    for exporter in exporters:
        assert exporter.group != "speaker"


@pytest.mark.django_db
def test_schedule_export_view_tablist_has_expected_keys(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportView, request)

    tablist = view.tablist()

    assert set(tablist.keys()) == {"custom", "general", "api"}


@pytest.mark.django_db
def test_schedule_release_view_get_form_kwargs_passes_event_and_locales(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleReleaseView, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event
    assert kwargs["locales"] == event.locales


@pytest.mark.django_db
def test_schedule_release_view_warnings_from_wip_schedule(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleReleaseView, request)

    with scopes_disabled():
        warnings = view.warnings

    assert isinstance(warnings, dict)


@pytest.mark.django_db
def test_schedule_release_view_changes_from_wip_schedule(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleReleaseView, request)

    with scopes_disabled():
        changes = view.changes

    assert isinstance(changes, dict)


@pytest.mark.django_db
def test_schedule_release_view_notifications_count(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleReleaseView, request)

    with scopes_disabled():
        notifications = view.notifications

    assert isinstance(notifications, int)


@pytest.mark.django_db
def test_serialize_break_with_room(event):
    with scopes_disabled():
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


@pytest.mark.django_db
def test_serialize_break_without_room(event):
    with scopes_disabled():
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=None, is_visible=True
        )

    result = serialize_break(slot)

    assert result["id"] == slot.pk
    assert result["room"] is None
    assert result["start"] is None
    assert result["end"] is None


@pytest.mark.django_db
def test_serialize_slot_with_submission(talk_slot):
    with scopes_disabled():
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


@pytest.mark.django_db
def test_serialize_slot_with_submission_and_track(event):
    with scopes_disabled():
        track = TrackFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, track=track
        )
        slot = TalkSlotFactory(submission=submission, is_visible=True)

    with scopes_disabled():
        result = serialize_slot(slot)

    assert result["track"]["name"] == str(track.name)
    assert result["track"]["color"] == track.color


@pytest.mark.django_db
def test_serialize_slot_without_track(talk_slot):
    with scopes_disabled():
        talk_slot.submission.track = None
        talk_slot.submission.save()
        result = serialize_slot(talk_slot)

    assert result["track"] is None


@pytest.mark.django_db
def test_serialize_slot_with_warnings(talk_slot):
    warnings = ["Speaker is unavailable", "Room conflict"]

    with scopes_disabled():
        result = serialize_slot(talk_slot, warnings=warnings)

    assert result["warnings"] == warnings


@pytest.mark.django_db
def test_serialize_slot_without_warnings(talk_slot):
    with scopes_disabled():
        result = serialize_slot(talk_slot)

    assert result["warnings"] == []


@pytest.mark.django_db
def test_serialize_slot_break_without_submission(event):
    with scopes_disabled():
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=room, is_visible=True
        )

    result = serialize_slot(slot)

    assert result["id"] == slot.pk
    assert result["room"] == room.pk
    assert "speakers" not in result
    assert "state" not in result


@pytest.mark.django_db
def test_talk_update_get_object_returns_slot(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TalkUpdate, request, pk=talk_slot.pk)

    with scopes_disabled():
        result = view.get_object()

    assert result == talk_slot


@pytest.mark.django_db
def test_talk_update_get_object_returns_none_for_missing_slot(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(TalkUpdate, request, pk=999999)

    with scopes_disabled():
        result = view.get_object()

    assert result is None


@pytest.mark.django_db
def test_quick_schedule_view_get_object(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code)

    with scopes_disabled():
        result = view.get_object()

    assert result == talk_slot


@pytest.mark.django_db
def test_quick_schedule_view_get_object_case_insensitive(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code.lower())

    with scopes_disabled():
        result = view.get_object()

    assert result == talk_slot


@pytest.mark.django_db
def test_quick_schedule_view_get_form_kwargs_includes_event(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code)

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event


@pytest.mark.django_db
def test_quick_schedule_view_get_success_url(talk_slot):
    event = talk_slot.submission.event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(
        event, user=user, path="/orga/event/test/schedule/quick/ABC/"
    )
    view = make_view(QuickScheduleView, request, code=talk_slot.submission.code)

    assert view.get_success_url() == "/orga/event/test/schedule/quick/ABC/"


@pytest.mark.django_db
def test_room_view_get_queryset(event):
    with scopes_disabled():
        room1 = RoomFactory(event=event)
        room2 = RoomFactory(event=event)
        other_event_room = RoomFactory()  # different event
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "list"

    with scopes_disabled():
        result = set(view.get_queryset())

    assert result == {room1, room2}
    assert other_event_room not in result


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected_suffix"),
    (
        ("list", "orga_list"),
        ("detail", "orga_detail"),
        ("create", "create"),
        ("update", "update"),
        ("delete", "delete"),
    ),
)
def test_room_view_get_permission_required(event, action, expected_suffix):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = action

    perm = view.get_permission_required()

    assert perm == Room.get_perm(expected_suffix)


@pytest.mark.django_db
def test_room_view_get_generic_title_with_instance(event):
    with scopes_disabled():
        room = RoomFactory(event=event, name="Main Hall")
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)

    title = view.get_generic_title(instance=room)

    assert "Main Hall" in str(title)


@pytest.mark.django_db
def test_room_view_get_generic_title_create(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "create"

    title = view.get_generic_title()

    assert str(title) == "New room"


@pytest.mark.django_db
def test_room_view_get_generic_title_list(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(RoomView, request)
    view.action = "list"

    title = view.get_generic_title()

    assert str(title) == "Rooms"


@pytest.mark.django_db
def test_schedule_export_download_view_get_error_redirect_url(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportDownloadView, request)

    assert view.get_error_redirect_url() == event.orga_urls.schedule_export


@pytest.mark.django_db
def test_schedule_export_download_view_get_async_download_filename(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(ScheduleExportDownloadView, request)

    assert view.get_async_download_filename() == f"{event.slug}_schedule.zip"


@pytest.mark.django_db
def test_serialize_slot_speakers_list(event):
    """serialize_slot includes speaker display names."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, name="Test Speaker")
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)

    with scopes_disabled():
        result = serialize_slot(slot)

    assert len(result["speakers"]) == 1
    assert result["speakers"][0]["name"] == speaker.get_display_name()


@pytest.mark.django_db
def test_serialize_slot_do_not_record_flag(event):
    with scopes_disabled():
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, do_not_record=True
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)

    with scopes_disabled():
        result = serialize_slot(slot)

    assert result["do_not_record"] is True


@pytest.mark.django_db
def test_serialize_slot_content_locale(event):
    with scopes_disabled():
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, content_locale="de"
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)

    with scopes_disabled():
        result = serialize_slot(slot)

    assert result["content_locale"] == "de"
