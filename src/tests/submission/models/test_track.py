# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.models import SubmitterAccessCode, Track
from tests.factories import EventFactory, SubmitterAccessCodeFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_track_properties():
    track = TrackFactory(name="Web Security")

    assert str(track) == "Web Security"
    assert track.log_parent == track.event
    assert track.slug == f"{track.id}-web-security"


def test_track_ordering_by_position():
    event = EventFactory()
    track_b = TrackFactory(event=event, position=2)
    track_a = TrackFactory(event=event, position=1)

    assert list(event.tracks.all()) == [track_a, track_b]
    assert list(Track.get_order_queryset(event)) == [track_a, track_b]


def test_track_move_swaps_positions_and_stops_at_boundaries():
    event = EventFactory()
    first, second = (TrackFactory(event=event, position=i) for i in range(2))

    def positions():
        return [
            Track.objects.get(pk=first.pk).position,
            Track.objects.get(pk=second.pk).position,
        ]

    first.move(up=True)
    assert positions() == [0, 1]
    second.move(up=False)
    assert positions() == [0, 1]
    first.move(up=False)
    assert positions() == [1, 0]
    first.move(up=True)
    assert positions() == [0, 1]


def test_track_delete_removes_access_codes_left_without_tracks():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    single = SubmitterAccessCodeFactory(event=event)
    single.tracks.add(track1)
    multi = SubmitterAccessCodeFactory(event=event)
    multi.tracks.add(track1, track2)

    track1.delete()

    assert not SubmitterAccessCode.objects.filter(pk=single.pk).exists()
    assert list(multi.tracks.all()) == [track2]
