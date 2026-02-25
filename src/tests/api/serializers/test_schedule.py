import pytest
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError
from rest_framework.fields import DateTimeField as DRFDateTimeField

from pretalx.api.serializers.schedule import (
    ScheduleListSerializer,
    ScheduleReleaseSerializer,
    ScheduleSerializer,
    TalkSlotOrgaSerializer,
    TalkSlotSerializer,
)
from tests.factories import (
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_schedule_list_serializer_fields():
    with scopes_disabled():
        event = EventFactory()
        schedule = ScheduleFactory(event=event, version="v1")

        serializer = ScheduleListSerializer(
            schedule, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert set(data.keys()) == {"id", "version", "published"}
    assert data["id"] == schedule.pk
    assert data["version"] == "v1"
    assert data["published"] is None


@pytest.mark.django_db
def test_schedule_list_serializer_version_uses_fallback_for_wip():
    """WIP schedules (version=None) use 'wip' as fallback version string."""
    with scopes_disabled():
        event = EventFactory()
        schedule = event.wip_schedule

        serializer = ScheduleListSerializer(
            schedule, context={"request": make_api_request(event=event)}
        )

    assert schedule.version is None
    assert serializer.data["version"] == "wip"


@pytest.mark.django_db
def test_schedule_serializer_get_slots_returns_ids():
    """When slots are not expanded, get_slots returns a list of PKs."""
    with scopes_disabled():
        event = EventFactory()
        schedule = ScheduleFactory(event=event, version="v1")
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub, schedule=schedule, is_visible=True)

        serializer = ScheduleSerializer(
            schedule, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert list(data["slots"]) == [slot.pk]


@pytest.mark.django_db
def test_schedule_serializer_get_slots_filters_visible_only():
    """With only_visible_slots=True (default), non-visible slots are excluded."""
    with scopes_disabled():
        event = EventFactory()
        schedule = ScheduleFactory(event=event, version="v1")
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        visible_slot = TalkSlotFactory(
            submission=sub1, schedule=schedule, is_visible=True
        )
        TalkSlotFactory(submission=sub2, schedule=schedule, is_visible=False)

        serializer = ScheduleSerializer(
            schedule, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert list(data["slots"]) == [visible_slot.pk]


@pytest.mark.django_db
def test_schedule_serializer_get_slots_includes_all_when_not_only_visible():
    """With only_visible_slots=False, all slots are returned."""
    with scopes_disabled():
        event = EventFactory()
        schedule = ScheduleFactory(event=event, version="v1")
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        slot1 = TalkSlotFactory(submission=sub1, schedule=schedule, is_visible=True)
        slot2 = TalkSlotFactory(submission=sub2, schedule=schedule, is_visible=False)

        context = {"request": make_api_request(event=event)}
        context["only_visible_slots"] = False
        serializer = ScheduleSerializer(schedule, context=context)
        data = serializer.data

    assert set(data["slots"]) == {slot1.pk, slot2.pk}


@pytest.mark.django_db
def test_schedule_serializer_get_slots_returns_empty_for_unreleased_schedule():
    """WIP schedules return empty slots list when only_visible_slots is True,
    because unreleased schedules should never expose slot data publicly."""
    with scopes_disabled():
        event = EventFactory()
        schedule = event.wip_schedule
        sub = SubmissionFactory(event=event)
        TalkSlotFactory(submission=sub, schedule=schedule, is_visible=True)

        serializer = ScheduleSerializer(
            schedule, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert data["slots"] == []


@pytest.mark.django_db
def test_schedule_serializer_get_slots_expanded():
    """When slots are expanded via query param, get_slots returns serialized data."""
    with scopes_disabled():
        event = EventFactory()
        schedule = ScheduleFactory(event=event, version="v1")
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub, schedule=schedule, is_visible=True)

        request = make_api_request(event=event, data={"expand": "slots"})
        serializer = ScheduleSerializer(schedule, context={"request": request})
        data = serializer.data

    assert len(data["slots"]) == 1
    assert data["slots"][0]["id"] == slot.pk
    assert data["slots"][0]["submission"] == sub.code


@pytest.mark.django_db
def test_schedule_release_serializer_validate_version_rejects_duplicate():
    """validate_version raises ValidationError when the version already exists."""
    with scopes_disabled():
        event = EventFactory()
        ScheduleFactory(event=event, version="v1")

        context = {"request": make_api_request(event=event)}
        serializer = ScheduleReleaseSerializer(data={"version": "v1"}, context=context)

        assert not serializer.is_valid()
    assert "version" in serializer.errors


@pytest.mark.django_db
def test_schedule_release_serializer_validate_version_accepts_new_version():
    with scopes_disabled():
        event = EventFactory()

        context = {"request": make_api_request(event=event)}
        serializer = ScheduleReleaseSerializer(data={"version": "v1"}, context=context)

        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_schedule_release_serializer_comment_optional():
    """comment field is not required and accepts blank/null values."""
    with scopes_disabled():
        event = EventFactory()

        context = {"request": make_api_request(event=event)}
        serializer = ScheduleReleaseSerializer(
            data={"version": "v2", "comment": ""}, context=context
        )

        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_talk_slot_serializer_fields():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub)

        serializer = TalkSlotSerializer(
            slot, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert set(data.keys()) == {
        "id",
        "room",
        "start",
        "end",
        "submission",
        "schedule",
        "description",
        "duration",
    }
    assert data["id"] == slot.pk
    assert data["submission"] == sub.code
    assert data["room"] == slot.room_id
    assert data["schedule"] == slot.schedule_id
    assert data["duration"] == slot.duration


@pytest.mark.django_db
def test_talk_slot_serializer_end_uses_local_end():
    """The end field is sourced from local_end, not a stored end column."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub)

        serializer = TalkSlotSerializer(
            slot, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    expected = DRFDateTimeField().to_representation(slot.local_end)
    assert data["end"] == expected


@pytest.mark.django_db
def test_talk_slot_serializer_submission_is_read_only():
    serializer = TalkSlotSerializer()
    assert serializer.fields["submission"].read_only is True


@pytest.mark.django_db
def test_talk_slot_orga_serializer_includes_extra_fields():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub)

        serializer = TalkSlotOrgaSerializer(
            slot, context={"request": make_api_request(event=event)}
        )
        data = serializer.data

    assert data["is_visible"] == slot.is_visible
    assert data["slot_type"] == slot.slot_type


@pytest.mark.parametrize("field", ("end", "description"))
@pytest.mark.django_db
def test_talk_slot_orga_serializer_validate_rejects_when_submission_exists(field):
    """validate_end and validate_description raise ValidationError when the slot
    has a submission, because those fields must be changed via submission instead."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub)

    serializer = TalkSlotOrgaSerializer(
        instance=slot, data={}, context={"request": make_api_request(event=event)}
    )
    with pytest.raises(ValidationError):
        getattr(serializer, f"validate_{field}")("any value")


@pytest.mark.parametrize("field", ("end", "description"))
@pytest.mark.django_db
def test_talk_slot_orga_serializer_validate_allows_when_no_submission(field):
    """validate_end and validate_description allow editing when there is
    no associated submission (e.g. break slots)."""
    with scopes_disabled():
        event = EventFactory()
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(submission=None, room=room, schedule=event.wip_schedule)

    serializer = TalkSlotOrgaSerializer(
        instance=slot, data={}, context={"request": make_api_request(event=event)}
    )
    result = getattr(serializer, f"validate_{field}")("test value")

    assert result == "test value"


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_talk_slot_orga_serializer_update_recomputes_unreleased_changes(talk_slot):
    """Updating a slot via the orga serializer recomputes the
    unreleased schedule changes cache via the async task (eager in tests)."""
    event = talk_slot.schedule.event
    event.cache.delete("has_unreleased_schedule_changes")

    serializer = TalkSlotOrgaSerializer(
        instance=talk_slot, data={}, context={"request": make_api_request(event=event)}
    )
    with scopes_disabled():
        serializer.update(talk_slot, {})

    assert event.cache.get("has_unreleased_schedule_changes") is True
