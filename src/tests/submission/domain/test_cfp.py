# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.submission.domain.cfp import cfp_deadlines, submission_types_by_deadline
from tests.factories import EventFactory, SubmissionTypeFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_types_by_deadline_groups_types_per_deadline():
    event = EventFactory()
    moment = (now() + dt.timedelta(days=5)).replace(microsecond=0)
    SubmissionTypeFactory(event=event, deadline=moment)
    SubmissionTypeFactory(event=event, deadline=moment)
    SubmissionTypeFactory(event=event, deadline=None)

    grouped = submission_types_by_deadline(event)

    assert list(grouped.keys()) == [moment]
    assert len(grouped[moment]) == 2


def test_submission_types_by_deadline_empty_when_no_overrides():
    event = EventFactory()
    SubmissionTypeFactory(event=event, deadline=None)

    assert submission_types_by_deadline(event) == {}


def test_cfp_deadlines_includes_type_and_cfp_deadlines():
    event = EventFactory()
    deadline = (now() + dt.timedelta(days=5)).replace(microsecond=0)
    cfp_deadline = (now() + dt.timedelta(days=10)).replace(microsecond=0)
    event.cfp.deadline = cfp_deadline
    event.cfp.save()
    submission_type = SubmissionTypeFactory(event=event, deadline=deadline, name="Talk")

    result = cfp_deadlines(event)

    expected_type_dt = deadline.astimezone(event.tz)
    expected_cfp_dt = cfp_deadline.astimezone(event.tz)
    assert (expected_type_dt, submission_type) in result
    assert (expected_cfp_dt, None) in result


def test_cfp_deadlines_without_cfp_deadline():
    event = EventFactory()
    event.cfp.deadline = None
    event.cfp.save()
    deadline = (now() + dt.timedelta(days=5)).replace(microsecond=0)
    submission_type = SubmissionTypeFactory(event=event, deadline=deadline, name="Talk")

    result = cfp_deadlines(event)

    assert len(result) == 1
    assert result[0] == (deadline.astimezone(event.tz), submission_type)
