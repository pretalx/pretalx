# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict

from pretalx.common.models import ActivityLog
from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.common.tables.log import log_filters
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    RoomFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def build(event=None, query=""):
    context = FilterContext(event=event)
    return TableFilterSet(log_filters(context), data=QueryDict(query), context=context)


def action_values(filterset):
    return {choice.value for choice in filterset.filters["action_type"].choices}


def test_filters_are_dropped_without_an_event():
    assert build().facets == []


def test_object_type_choices_come_from_the_logs():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ActivityLogFactory(event=event, content_object=submission)

    filterset = build(event)

    content_type = ContentType.objects.get_for_model(submission)
    values = [c.value for c in filterset.filters["object_type"].choices]
    assert values == [str(content_type.id)]


def test_object_type_choices_exclude_other_events():
    event = EventFactory()
    other_event = EventFactory()
    other_submission = SubmissionFactory(event=other_event)
    ActivityLogFactory(event=other_event, content_object=other_submission)
    room = RoomFactory(event=event)
    ActivityLogFactory(event=event, content_object=room)

    filterset = build(event)

    room_type = ContentType.objects.get_for_model(room)
    values = [c.value for c in filterset.filters["object_type"].choices]
    assert values == [str(room_type.id)]


def test_action_type_choices_come_from_the_logs():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )

    assert action_values(build(event)) == {"pretalx.submission.create"}


def test_ungrouped_actions_land_in_a_group_of_their_own():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.custom.action"
    )
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.another.custom"
    )

    filterset = build(event)
    groups = {
        c.value: c.group
        for c in filterset.filters["action_type"].choices
        if c.value.startswith(("pretalx.custom", "pretalx.another"))
    }

    assert set(groups) == {"pretalx.custom.action", "pretalx.another.custom"}
    assert len(set(groups.values())) == 1


def test_filter_by_object_type():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=submission)
    content_type = ContentType.objects.get_for_model(submission)

    filterset = build(event, f"object_type={content_type.id}")

    assert list(filterset.filter(ActivityLog.objects.filter(event=event))) == [log]


def test_filter_by_action_type():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    created = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.update"
    )

    filterset = build(event, "action_type=pretalx.submission.create")

    assert list(filterset.filter(ActivityLog.objects.filter(event=event))) == [created]


def test_without_filters_everything_is_returned():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    first = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )
    second = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.update"
    )

    filterset = build(event)

    assert set(filterset.filter(ActivityLog.objects.filter(event=event))) == {
        first,
        second,
    }


def test_filters_combine():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    content_type = ContentType.objects.get_for_model(submission)
    match = ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.create"
    )
    ActivityLogFactory(
        event=event, content_object=submission, action_type="pretalx.submission.update"
    )
    ActivityLogFactory(
        event=event, content_object=room, action_type="pretalx.room.create"
    )

    filterset = build(
        event, f"object_type={content_type.id}&action_type=pretalx.submission.create"
    )

    assert list(filterset.filter(ActivityLog.objects.filter(event=event))) == [match]
