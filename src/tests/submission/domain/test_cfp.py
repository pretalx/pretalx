# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.submission.domain.cfp import (
    access_code_blocker,
    can_submit_without_access_code,
    cfp_deadlines,
    submission_types_by_deadline,
)
from tests.factories import EventFactory, SubmissionTypeFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_types_by_deadline_groups_types_per_deadline():
    event = EventFactory()
    SubmissionTypeFactory(event=event, deadline=None)
    assert submission_types_by_deadline(event) == {}

    moment = (now() + dt.timedelta(days=5)).replace(microsecond=0)
    first = SubmissionTypeFactory(event=event, deadline=moment)
    second = SubmissionTypeFactory(event=event, deadline=moment)

    assert submission_types_by_deadline(event) == {moment: [first, second]}


def test_cfp_deadlines_includes_type_and_cfp_deadlines():
    event = EventFactory()
    deadline = (now() + dt.timedelta(days=5)).replace(microsecond=0)
    cfp_deadline = (now() + dt.timedelta(days=10)).replace(microsecond=0)
    event.cfp.deadline = cfp_deadline
    event.cfp.save()
    submission_type = SubmissionTypeFactory(event=event, deadline=deadline, name="Talk")

    assert cfp_deadlines(event) == [
        (deadline.astimezone(event.tz), submission_type),
        (cfp_deadline.astimezone(event.tz), None),
    ]

    event.cfp.deadline = None
    event.cfp.save()

    assert cfp_deadlines(event) == [(deadline.astimezone(event.tz), submission_type)]


@pytest.mark.parametrize(
    ("restrict_existing", "type_deadline", "open_types", "expected"),
    (
        (False, None, 0, None),
        (True, None, 0, "submission_type"),
        (True, None, 1, None),
        (False, dt.timedelta(days=-1), 0, "submission_type"),
    ),
    ids=[
        "unrestricted_type",
        "all_types_restricted",
        "one_unrestricted_type_left",
        "all_types_past_deadline",
    ],
)
def test_access_code_blocker_types(
    restrict_existing, type_deadline, open_types, expected
):
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=5))
    event.submission_types.update(
        requires_access_code=restrict_existing,
        deadline=now() + type_deadline if type_deadline else None,
    )
    SubmissionTypeFactory.create_batch(
        open_types, event=event, requires_access_code=False
    )

    assert access_code_blocker(event) == expected
    assert can_submit_without_access_code(event) is (expected is None)


@pytest.mark.parametrize(
    ("track_visibility", "use_tracks", "track_access_codes", "expected"),
    (
        ("required", True, (True,), "track"),
        ("required", True, (True, False), None),
        ("optional", True, (True,), None),
        ("required", True, (), None),
        ("required", False, (True,), None),
    ),
    ids=[
        "all_tracks_restricted",
        "unrestricted_track_left",
        "track_optional",
        "no_tracks",
        "tracks_disabled",
    ],
)
def test_access_code_blocker_tracks(
    track_visibility, use_tracks, track_access_codes, expected
):
    event = EventFactory(
        cfp__fields={"track": {"visibility": track_visibility}},
        feature_flags={"use_tracks": use_tracks},
    )
    for requires_access_code in track_access_codes:
        TrackFactory(event=event, requires_access_code=requires_access_code)

    assert access_code_blocker(event) == expected
