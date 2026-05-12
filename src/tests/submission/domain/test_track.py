# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.domain.track import can_delete_track
from tests.factories import EventFactory, SubmissionFactory, TrackFactory

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
