# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.common.domain.queries.log import actions_by, event_activity_log
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
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
