# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.submission.models.cfp import default_fields
from tests.factories import EventFactory, SubmissionTypeFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_cfp_default_fields_returns_deep_copy():
    fields1 = default_fields()
    fields2 = default_fields()
    assert fields1 == fields2
    fields1["title"]["visibility"] = "changed"
    assert fields2["title"]["visibility"] != "changed"


def test_cfp_str():
    event = EventFactory()
    assert str(event.cfp) == f"CfP(event={event.slug})"


def test_cfp_field_flags_follow_fields_with_defaults():
    event = EventFactory()
    cfp = event.cfp

    assert {
        "request_title": cfp.request_title,
        "request_abstract": cfp.request_abstract,
        "request_availabilities": cfp.request_availabilities,
        "request_track": cfp.request_track,
        "require_title": cfp.require_title,
        "require_description": cfp.require_description,
        "require_availabilities": cfp.require_availabilities,
    } == {
        "request_title": True,
        "request_abstract": True,
        "request_availabilities": False,
        "request_track": False,
        "require_title": True,
        "require_description": False,
        "require_availabilities": False,
    }
    assert cfp.max_speakers is None
    assert cfp.tag_limits == (None, None)

    cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 3}
    cfp.fields["tags"] = {"visibility": "optional", "min": 1, "max": 5}
    assert cfp.max_speakers == 3
    assert cfp.tag_limits == (1, 5)

    cfp.fields = {}
    assert cfp.request_title is True
    assert cfp.max_speakers is None
    assert cfp.tag_limits == (None, None)


@pytest.mark.parametrize(
    (
        "opening_offset",
        "deadline_offset",
        "before_opening",
        "after_deadline",
        "is_open",
        "has_max_deadline",
    ),
    (
        (None, None, False, False, True, False),
        (dt.timedelta(days=7), dt.timedelta(days=14), True, False, False, True),
        (dt.timedelta(days=-7), None, False, False, True, False),
        (None, dt.timedelta(days=-7), False, True, False, True),
        (None, dt.timedelta(days=7), False, False, True, True),
        (dt.timedelta(days=-7), dt.timedelta(days=7), False, False, True, True),
    ),
    ids=[
        "no_dates",
        "before_opening",
        "past_opening_no_deadline",
        "after_deadline",
        "future_deadline",
        "between_opening_and_deadline",
    ],
)
def test_cfp_open_state(
    opening_offset,
    deadline_offset,
    before_opening,
    after_deadline,
    is_open,
    has_max_deadline,
):
    opening = now() + opening_offset if opening_offset else None
    deadline = now() + deadline_offset if deadline_offset else None
    event = EventFactory(cfp__opening=opening, cfp__deadline=deadline)

    with scope(event=event):
        assert event.cfp.before_opening is before_opening
        assert event.cfp.after_deadline is after_deadline
        assert event.cfp.is_open is is_open
        assert event.cfp.max_deadline == (deadline if has_max_deadline else None)


@pytest.mark.parametrize(
    ("deadline_offset", "restrict_types", "expected"),
    (
        (dt.timedelta(days=7), False, True),
        (dt.timedelta(days=7), True, False),
        (dt.timedelta(days=-7), False, False),
    ),
    ids=["open", "open_but_restricted", "closed"],
)
def test_cfp_is_open_without_access_code(deadline_offset, restrict_types, expected):
    event = EventFactory(cfp__deadline=now() + deadline_offset)
    if restrict_types:
        event.submission_types.update(requires_access_code=True)

    with scope(event=event):
        assert event.cfp.is_open_without_access_code is expected


def test_cfp_future_type_deadline_keeps_cfp_open():
    type_deadline = now() + dt.timedelta(days=14)
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=7))
    SubmissionTypeFactory(event=event, deadline=type_deadline)

    with scope(event=event):
        assert event.cfp.max_deadline == type_deadline
        assert event.cfp.after_deadline is False
        assert event.cfp.is_open is True


def test_cfp_copy_data_from():
    source_event = EventFactory(
        cfp__headline="Test Headline", cfp__deadline=now() + dt.timedelta(days=30)
    )
    full_target = EventFactory()
    partial_target = EventFactory()
    original_deadline = partial_target.cfp.deadline

    full_target.cfp.copy_data_from(source_event.cfp)
    partial_target.cfp.copy_data_from(source_event.cfp, skip_attributes=["deadline"])
    full_target.cfp.refresh_from_db()
    partial_target.cfp.refresh_from_db()

    assert full_target.cfp.headline == source_event.cfp.headline
    assert full_target.cfp.deadline == source_event.cfp.deadline
    assert partial_target.cfp.headline == source_event.cfp.headline
    assert partial_target.cfp.deadline == original_deadline
