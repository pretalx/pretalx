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


def test_apply_track_field_changes_pins_on_signup_unset():
    event = EventFactory()
    track = TrackFactory(event=event, attendee_signup_required=False)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = apply_track_field_changes(track, ["attendee_signup_required"])

        submission.refresh_from_db()
    assert pinned == [submission]
    assert submission.attendee_signup_required is True


def test_apply_track_field_changes_no_op_when_field_unchanged():
    event = EventFactory()
    track = TrackFactory(event=event, attendee_signup_required=False)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = apply_track_field_changes(track, ["name"])

        submission.refresh_from_db()
    assert pinned == []
    assert submission.attendee_signup_required is None


def test_apply_track_field_changes_no_op_when_signup_set_to_true():
    event = EventFactory()
    track = TrackFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, track=track)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)

        pinned = apply_track_field_changes(track, ["attendee_signup_required"])

        submission.refresh_from_db()
    assert pinned == []
    assert submission.attendee_signup_required is None
