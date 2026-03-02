# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.submission.models.cfp import default_fields, default_settings
from tests.factories import EventFactory, SubmissionTypeFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_cfp_default_settings():
    assert default_settings() == {
        "flow": {},
        "count_length_in": "chars",
        "show_deadline": True,
    }


def test_cfp_default_fields_returns_deep_copy():
    fields1 = default_fields()
    fields2 = default_fields()
    assert fields1 == fields2
    fields1["title"]["visibility"] = "changed"
    assert fields2["title"]["visibility"] != "changed"


def test_cfp_str():
    event = EventFactory()
    assert str(event.cfp) == f"CfP(event={event.slug})"


@pytest.mark.parametrize(
    ("field", "expected_requested"),
    (("title", True), ("abstract", True), ("availabilities", False), ("track", False)),
)
def test_cfp_request_field(field, expected_requested):
    event = EventFactory()
    assert getattr(event.cfp, f"request_{field}") is expected_requested


@pytest.mark.parametrize(
    ("field", "expected_required"),
    (("title", True), ("description", False), ("availabilities", False)),
)
def test_cfp_require_field(field, expected_required):
    event = EventFactory()
    assert getattr(event.cfp, f"require_{field}") is expected_required


def test_cfp_request_field_uses_default_for_missing_key():
    event = EventFactory()
    event.cfp.fields = {}
    assert event.cfp.request_title is True


@pytest.mark.parametrize(
    ("opening_offset", "expected"),
    ((dt.timedelta(days=7), True), (dt.timedelta(days=-7), False), (None, False)),
    ids=["future_opening", "past_opening", "no_opening"],
)
def test_cfp_before_opening(opening_offset, expected):
    opening = now() + opening_offset if opening_offset else None
    event = EventFactory(cfp__opening=opening)
    with scope(event=event):
        assert event.cfp.before_opening is expected


@pytest.mark.parametrize(
    ("deadline_offset", "expected"),
    ((dt.timedelta(days=-7), True), (dt.timedelta(days=7), False), (None, False)),
    ids=["past_deadline", "future_deadline", "no_deadline"],
)
def test_cfp_after_deadline(deadline_offset, expected):
    deadline = now() + deadline_offset if deadline_offset else None
    event = EventFactory(cfp__deadline=deadline)
    with scope(event=event):
        assert event.cfp.after_deadline is expected


@pytest.mark.parametrize(
    ("opening_offset", "deadline_offset", "expected"),
    (
        (None, None, True),
        (dt.timedelta(days=7), dt.timedelta(days=14), False),
        (None, dt.timedelta(days=-7), False),
        (dt.timedelta(days=-7), dt.timedelta(days=7), True),
    ),
    ids=[
        "no_dates",
        "before_opening",
        "after_deadline",
        "between_opening_and_deadline",
    ],
)
def test_cfp_is_open(opening_offset, deadline_offset, expected):
    opening = now() + opening_offset if opening_offset else None
    deadline = now() + deadline_offset if deadline_offset else None
    event = EventFactory(cfp__opening=opening, cfp__deadline=deadline)
    with scope(event=event):
        assert event.cfp.is_open is expected


def test_cfp_max_deadline_cfp_only():
    deadline = now() + dt.timedelta(days=7)
    event = EventFactory(cfp__deadline=deadline)
    with scope(event=event):
        assert event.cfp.max_deadline == deadline


def test_cfp_max_deadline_none_when_no_deadlines():
    event = EventFactory(cfp__deadline=None)
    with scope(event=event):
        assert event.cfp.max_deadline is None


def test_cfp_max_deadline_considers_submission_type_deadlines():
    """max_deadline returns the latest deadline across CfP and submission types."""
    cfp_deadline = now() + dt.timedelta(days=7)
    type_deadline = now() + dt.timedelta(days=14)
    event = EventFactory(cfp__deadline=cfp_deadline)
    SubmissionTypeFactory(event=event, deadline=type_deadline)

    with scope(event=event):
        assert event.cfp.max_deadline == type_deadline


def test_cfp_after_deadline_false_when_type_deadline_future():
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=7))
    SubmissionTypeFactory(event=event, deadline=now() + dt.timedelta(days=14))

    with scope(event=event):
        assert not event.cfp.after_deadline


def test_cfp_is_open_with_future_type_deadline():
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=7))
    SubmissionTypeFactory(event=event, deadline=now() + dt.timedelta(days=14))

    with scope(event=event):
        assert event.cfp.is_open is True


def test_cfp_max_speakers_default():
    event = EventFactory()
    assert event.cfp.max_speakers is None


def test_cfp_max_speakers_custom():
    event = EventFactory()
    event.cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 3}
    assert event.cfp.max_speakers == 3


def test_cfp_max_speakers_missing_field_uses_default():
    event = EventFactory()
    event.cfp.fields = {}
    assert event.cfp.max_speakers is None


def test_cfp_tag_limits_default():
    event = EventFactory()
    assert event.cfp.tag_limits == (None, None)


def test_cfp_tag_limits_custom():
    event = EventFactory()
    event.cfp.fields["tags"] = {"visibility": "optional", "min": 1, "max": 5}
    assert event.cfp.tag_limits == (1, 5)


def test_cfp_tag_limits_missing_field_uses_default():
    event = EventFactory()
    event.cfp.fields = {}
    assert event.cfp.tag_limits == (None, None)


def test_cfp_copy_data_from():
    source_event = EventFactory(
        cfp__headline="Test Headline", cfp__deadline=now() + dt.timedelta(days=30)
    )
    target_event = EventFactory()

    target_event.cfp.copy_data_from(source_event.cfp)
    target_event.cfp.refresh_from_db()

    assert target_event.cfp.headline == source_event.cfp.headline
    assert target_event.cfp.deadline == source_event.cfp.deadline


def test_cfp_copy_data_from_with_skip():
    source_event = EventFactory(
        cfp__headline="New Headline", cfp__deadline=now() + dt.timedelta(days=30)
    )
    target_event = EventFactory()
    original_deadline = target_event.cfp.deadline

    target_event.cfp.copy_data_from(source_event.cfp, skip_attributes=["deadline"])
    target_event.cfp.refresh_from_db()

    assert target_event.cfp.headline == source_event.cfp.headline
    assert target_event.cfp.deadline == original_deadline
