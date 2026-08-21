# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.contenttypes.models import ContentType
from django_scopes import scope

from pretalx.common.domain.queries.log import actions_by, event_activity_log
from pretalx.common.models.log import ActivityLog
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_actions_by_filters_by_actor():
    user = UserFactory()
    user.log_action("pretalx.user.test_action")

    actions = actions_by(user)

    assert actions.count() == 1
    assert actions.first().person == user


def test_actions_by_excludes_other_actors():
    user = UserFactory()
    other = UserFactory()
    other.log_action("pretalx.user.test", person=other)

    assert list(actions_by(user)) == []


@pytest.mark.parametrize("item_count", (1, 3))
def test_actions_by_prefetches_actor_and_object_event(
    django_assert_num_queries, item_count
):
    user = UserFactory()
    objects = []
    for _ in range(item_count):
        event = EventFactory()
        objects += [SubmissionFactory(event=event), QuestionFactory(event=event)]
    for obj in objects:
        ActivityLogFactory(
            event=obj.event,
            person=user,
            content_object=obj,
            action_type="pretalx.submission.update",
        )

    with django_assert_num_queries(4):
        actions = list(actions_by(user))

        assert [action.person for action in actions] == [user] * len(objects)
        assert {action.content_object for action in actions} == set(objects)
        assert [action.content_object.event for action in actions] == [
            action.event for action in actions
        ]


def test_event_activity_log_filters_by_event():
    event = EventFactory()
    other = EventFactory()
    with scope(event=event):
        ActivityLogFactory(event=event, action_type="pretalx.event.update")
    with scope(event=other):
        ActivityLogFactory(event=other, action_type="pretalx.event.update")

    qs = event_activity_log(event)

    assert qs.count() == 1
    assert qs.first().event == event


def test_event_activity_log_prefetches_submission_content_object(
    django_assert_num_queries,
):
    event = EventFactory()
    with scope(event=event):
        sub = SubmissionFactory(event=event)
        for _ in range(3):
            ActivityLogFactory(
                event=event, content_object=sub, action_type="pretalx.submission.update"
            )

        qs = list(event_activity_log(event))
        # accessing content_object on each row should not re-query
        with django_assert_num_queries(0):
            for log in qs:
                assert log.content_object == sub


def test_event_activity_log_prefetch_ignores_uninstalled_model():
    event = EventFactory()
    stale_type = ContentType.objects.create(app_label="ghost_plugin", model="ghost")
    with scope(event=event):
        sub = SubmissionFactory(event=event)
        good = ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.update"
        )
        stale = ActivityLog.objects.create(
            event=event,
            content_type=stale_type,
            object_id=1,
            action_type="pretalx.submission.update",
        )

        logs = {log.pk: log for log in event_activity_log(event)}

    assert set(logs) == {good.pk, stale.pk}
    assert logs[good.pk].content_object == sub
    assert logs[stale.pk].content_object is None
