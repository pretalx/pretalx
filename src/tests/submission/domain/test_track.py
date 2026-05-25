# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.domain.track import apply_track_field_changes, can_delete_track
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_can_delete_track_true_for_unused():
    event = EventFactory()
    track = TrackFactory(event=event)

    with scope(event=event):
        assert can_delete_track(track) is True


def test_can_delete_track_false_when_used():
    event = EventFactory()
    track = TrackFactory(event=event)
    SubmissionFactory(event=event, track=track)

    with scope(event=event):
        assert can_delete_track(track) is False


@pytest.mark.parametrize(
    ("track_required", "changed_fields", "expect_pinned"),
    (
        (False, ["attendee_signup_required"], True),
        (False, ["name"], False),
        (True, ["attendee_signup_required"], False),
    ),
    ids=(
        "pins_on_signup_unset",
        "no_op_when_field_unchanged",
        "no_op_when_signup_set_to_true",
    ),
)
def test_apply_track_field_changes(track_required, changed_fields, expect_pinned):
    event = EventFactory()
    track = TrackFactory(event=event, attendee_signup_required=track_required)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = apply_track_field_changes(track, changed_fields)

        submission.refresh_from_db()
    if expect_pinned:
        assert pinned == [submission]
        assert submission.attendee_signup_required is True
    else:
        assert pinned == []
        assert submission.attendee_signup_required is None
