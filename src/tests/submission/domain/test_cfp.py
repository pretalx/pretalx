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


@pytest.mark.parametrize(
    ("restrict_existing", "open_types", "expected"),
    ((False, 0, None), (True, 0, "submission_type"), (True, 1, None)),
    ids=["unrestricted_type", "all_types_restricted", "one_unrestricted_type_left"],
)
def test_access_code_blocker_types(restrict_existing, open_types, expected):
    event = EventFactory()
    event.submission_types.update(requires_access_code=restrict_existing)
    SubmissionTypeFactory.create_batch(
        open_types, event=event, requires_access_code=False
    )

    assert access_code_blocker(event) == expected


def test_access_code_blocker_all_types_past_deadline():
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=5))
    event.submission_types.update(deadline=now() - dt.timedelta(days=1))

    assert access_code_blocker(event) == "submission_type"


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


@pytest.mark.parametrize("restrict_types", (True, False))
def test_can_submit_without_access_code(restrict_types):
    event = EventFactory()
    event.submission_types.update(requires_access_code=restrict_types)

    assert can_submit_without_access_code(event) is not restrict_types
