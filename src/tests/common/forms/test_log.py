# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.contenttypes.models import ContentType

from pretalx.common.forms.log import LogFilterForm
from pretalx.common.models import ActivityLog
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    RoomFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_logfilterform_init_without_event():
    form = LogFilterForm()
    assert "object_type" in form.fields
    assert "action_type" in form.fields


def test_logfilterform_object_type_choices_from_logs():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    ActivityLogFactory(event=event, content_object=sub)

    form = LogFilterForm(event=event)

    choices = dict(form.fields["object_type"].choices)
    assert "" in choices
    ct = ContentType.objects.get_for_model(sub)
    assert ct.id in choices


def test_logfilterform_object_type_excludes_unrelated_events():
    event = EventFactory()
    other_event = EventFactory()
    other_sub = SubmissionFactory(event=other_event)
    ActivityLogFactory(event=other_event, content_object=other_sub)

    form = LogFilterForm(event=event)

    ct = ContentType.objects.get_for_model(other_sub)
    choice_ids = [c[0] for c in form.fields["object_type"].choices]
    assert ct.id not in choice_ids


def test_logfilterform_action_type_choices_from_logs():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.create"
    )

    form = LogFilterForm(event=event)

    all_actions = set()
    for choice in form.fields["action_type"].choices:
        if isinstance(choice[1], list):
            for action_type, _label in choice[1]:
                all_actions.add(action_type)
        else:
            all_actions.add(choice[0])
    assert "pretalx.submission.create" in all_actions


def test_logfilterform_ungrouped_action_added_to_other():
    """Action types not in ACTION_TYPE_GROUPS appear under 'Other'."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.custom.action"
    )
    ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.another.custom"
    )

    form = LogFilterForm(event=event)

    other_actions = []
    for choice in form.fields["action_type"].choices:
        if isinstance(choice[1], list):
            other_actions.extend(action_type for action_type, _label in choice[1])
    assert "pretalx.custom.action" in other_actions
    assert "pretalx.another.custom" in other_actions


def test_logfilterform_filter_queryset_by_object_type():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=sub)
    ct = ContentType.objects.get_for_model(sub)

    data = {"object_type": str(ct.id), "action_type": ""}
    form = LogFilterForm(data=data, event=event)
    assert form.is_valid(), form.errors
    qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log]


def test_logfilterform_filter_queryset_by_action_type():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    log_create = ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.create"
    )
    ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.update"
    )

    data = {"object_type": "", "action_type": "pretalx.submission.create"}
    form = LogFilterForm(data=data, event=event)
    assert form.is_valid(), form.errors
    qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log_create]


def test_logfilterform_filter_queryset_empty_filters_returns_all():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    log1 = ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.create"
    )
    log2 = ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.update"
    )

    data = {"object_type": "", "action_type": ""}
    form = LogFilterForm(data=data, event=event)
    assert form.is_valid(), form.errors
    qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert set(qs) == {log1, log2}


def test_logfilterform_filter_queryset_by_both_type_and_action():
    """Applying both object_type and action_type filters narrows results."""
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    sub_ct = ContentType.objects.get_for_model(sub)
    log_match = ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.create"
    )
    ActivityLogFactory(
        event=event, content_object=sub, action_type="pretalx.submission.update"
    )
    ActivityLogFactory(
        event=event, content_object=room, action_type="pretalx.room.create"
    )

    data = {"object_type": str(sub_ct.id), "action_type": "pretalx.submission.create"}
    form = LogFilterForm(data=data, event=event)
    assert form.is_valid(), form.errors
    qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log_match]
