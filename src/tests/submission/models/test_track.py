import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmitterAccessCode, Track
from tests.factories import SubmitterAccessCodeFactory, TrackFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_track_str():
    track = TrackFactory(name="Security")
    assert str(track) == "Security"


@pytest.mark.django_db
def test_track_log_parent_is_event():
    track = TrackFactory()
    assert track.log_parent == track.event


@pytest.mark.django_db
def test_track_log_prefix():
    track = TrackFactory()
    assert track.log_prefix == "pretalx.track"


@pytest.mark.django_db
def test_track_slug():
    track = TrackFactory(name="Web Security")
    assert track.slug == f"{track.id}-web-security"


@pytest.mark.django_db
def test_track_get_order_queryset(event):
    track2 = TrackFactory(event=event, position=1)
    track1 = TrackFactory(event=event, position=0)

    with scopes_disabled():
        result = list(Track.get_order_queryset(event))

    assert result == [track1, track2]


@pytest.mark.django_db
def test_track_ordering_by_position(event):
    track_b = TrackFactory(event=event, position=2)
    track_a = TrackFactory(event=event, position=1)

    with scopes_disabled():
        tracks = list(event.tracks.all())

    assert tracks == [track_a, track_b]


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, False), (1, True)), ids=["down", "up"]
)
@pytest.mark.django_db
def test_track_move_swaps_positions(event, move_index, up):
    tracks = [TrackFactory(event=event, position=i) for i in range(2)]

    with scopes_disabled():
        tracks[move_index].move(up=up)

    for track in tracks:
        track.refresh_from_db()
    assert tracks[0].position == 1
    assert tracks[1].position == 0


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, True), (1, False)), ids=["up_at_top", "down_at_bottom"]
)
@pytest.mark.django_db
def test_track_move_noop_at_boundary(event, move_index, up):
    tracks = [TrackFactory(event=event, position=i) for i in range(2)]

    with scopes_disabled():
        tracks[move_index].move(up=up)

    for track in tracks:
        track.refresh_from_db()
    assert tracks[0].position == 0
    assert tracks[1].position == 1


@pytest.mark.django_db
def test_track_delete_removes_single_track_access_codes(event):
    """Deleting a track removes access codes that only reference that track."""
    track = TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track)

    with scopes_disabled():
        track.delete()
        assert not SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()


@pytest.mark.django_db
def test_track_delete_keeps_multi_track_access_codes(event):
    """Deleting a track preserves access codes that also reference other tracks."""
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track1, track2)

    with scopes_disabled():
        track1.delete()
        assert SubmitterAccessCode.objects.filter(pk=access_code.pk).exists()
