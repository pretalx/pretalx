# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict

from pretalx.common.models import ActivityLog
from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.common.tables.log import content_type_label, log_filters
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    RoomFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def build(event=None, query=""):
    context = FilterContext(event=event)
    return TableFilterSet(log_filters(context), data=QueryDict(query), context=context)


def test_filters_are_dropped_without_an_event():
    assert build().facets == []


def test_object_type_choices_come_from_the_event_logs():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    ActivityLogFactory(event=event, content_object=submission)
    ActivityLogFactory(event=event, content_object=room)
    other_event = EventFactory()
    ActivityLogFactory(
        event=other_event, content_object=TrackFactory(event=other_event)
    )

    filterset = build(event)

    assert [
        (c.value, str(c.label)) for c in filterset.filters["object_type"].choices
    ] == [
        (str(ContentType.objects.get_for_model(submission).id), "Proposals"),
        (str(ContentType.objects.get_for_model(room).id), "Rooms"),
    ]


def test_object_type_label_falls_back_to_the_content_type_name():
    content_type = ContentType.objects.create(
        app_label="pretalx_uninstalled_plugin", model="gone"
    )

    assert content_type.model_class() is None
    assert content_type_label(content_type) == "gone"


def test_action_type_choices_are_grouped_by_object_type():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )
    ActivityLogFactory(
        event=event, content_object=room, action_type="pretalx.room.update"
    )

    filterset = build(event)

    assert [
        (c.group, str(c.label), c.value)
        for c in filterset.filters["action_type"].choices
    ] == [
        ("Proposals", "Created", "pretalx.submission.create"),
        ("Rooms", "Modified", "pretalx.room.update"),
    ]


def test_action_type_choices_group_plugin_actions_by_their_object_type():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ActivityLogFactory(
        event=event,
        content_object=submission,
        action_type="pretalx_plugin.thing.frobbed",
    )

    filterset = build(event)

    assert [
        (c.group, str(c.label)) for c in filterset.filters["action_type"].choices
    ] == [("Proposals", "Frobbed")]


def test_action_type_is_grouped_with_its_most_common_object_type():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=room, action_type="pretalx.room.delete"
    )
    for _index in range(2):
        ActivityLogFactory(
            event=event, content_object=submission, action_type="pretalx.room.delete"
        )

    filterset = build(event)

    assert [
        (c.group, str(c.label)) for c in filterset.filters["action_type"].choices
    ] == [("Proposals", "Deleted")]


def test_action_type_group_falls_back_to_the_content_type_name():
    event = EventFactory()
    stale_type = ContentType.objects.create(
        app_label="pretalx_uninstalled_plugin", model="gone"
    )
    ActivityLog.objects.create(
        event=event,
        content_type=stale_type,
        object_id=1,
        action_type="pretalx.gone.soft_delete",
    )

    filterset = build(event)

    assert [
        (c.group, str(c.label)) for c in filterset.filters["action_type"].choices
    ] == [("gone", "Soft delete")]


def test_filters_narrow_and_combine():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    content_type = ContentType.objects.get_for_model(submission)
    created = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )
    updated = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.update"
    )
    room_created = ActivityLogFactory(
        event=event, content_object=room, action_type="pretalx.room.create"
    )
    logs = ActivityLog.objects.filter(event=event)

    def filtered(query):
        return set(build(event, query).filter(logs))

    assert filtered("") == {created, updated, room_created}
    assert filtered(f"object_type={content_type.id}") == {created, updated}
    assert filtered("action_type=pretalx.submission.create") == {created}
    assert filtered(
        f"object_type={content_type.id}&action_type=pretalx.submission.create"
    ) == {created}
