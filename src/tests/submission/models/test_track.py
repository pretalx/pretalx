# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.models import SubmitterAccessCode, Track
from tests.factories import EventFactory, SubmitterAccessCodeFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_track_str():
    track = TrackFactory(name="Security")
    assert str(track) == "Security"


def test_track_log_parent_is_event():
    track = TrackFactory()
    assert track.log_parent == track.event


def test_track_log_prefix():
    track = TrackFactory()
    assert track.log_prefix == "pretalx.track"


def test_track_slug():
    track = TrackFactory(name="Web Security")
    assert track.slug == f"{track.id}-web-security"


def test_track_get_order_queryset():
    event = EventFactory()
    track2 = TrackFactory(event=event, position=1)
    track1 = TrackFactory(event=event, position=0)

    result = list(Track.get_order_queryset(event))

    assert result == [track1, track2]


def test_track_ordering_by_position():
    event = EventFactory()
    track_b = TrackFactory(event=event, position=2)
    track_a = TrackFactory(event=event, position=1)

    tracks = list(event.tracks.all())

    assert tracks == [track_a, track_b]


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, False), (1, True)), ids=["down", "up"]
)
def test_track_move_swaps_positions(move_index, up):
    event = EventFactory()
    tracks = [TrackFactory(event=event, position=i) for i in range(2)]

    tracks[move_index].move(up=up)

    for track in tracks:
        track.refresh_from_db()
    assert tracks[0].position == 1
    assert tracks[1].position == 0


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, True), (1, False)), ids=["up_at_top", "down_at_bottom"]
)
def test_track_move_noop_at_boundary(move_index, up):
    event = EventFactory()
    tracks = [TrackFactory(event=event, position=i) for i in range(2)]

    tracks[move_index].move(up=up)

    for track in tracks:
        track.refresh_from_db()
    assert tracks[0].position == 0
    assert tracks[1].position == 1


def test_track_delete_removes_single_track_access_codes():
    event = EventFactory()
    track = TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track)

    track.delete()
    assert not SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()


def test_track_delete_keeps_multi_track_access_codes():
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track1, track2)

    track1.delete()
    assert SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()
