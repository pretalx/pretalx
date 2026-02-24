import datetime as dt

import pytest
from django_scopes import scopes_disabled

from pretalx.schedule.models import Availability
from tests.factories import AvailabilityFactory, RoomFactory, SpeakerFactory

pytestmark = pytest.mark.unit


def _avail(start_hour, end_hour, day=1, month=1, year=2017, **kwargs):
    """Build an unsaved Availability with compact datetime specs.

    Not a factory: these pure-logic tests (overlaps, merge, union, intersection,
    etc.) need no DB at all. AvailabilityFactory would create an entire event
    object graph and hit the DB for every call, turning ~30 zero-DB tests into
    slow integration tests for no benefit.
    """
    return Availability(
        start=dt.datetime(year, month, day, start_hour),
        end=dt.datetime(year, month, day, end_hour),
        **kwargs,
    )


@pytest.mark.django_db
def test_availability_str_with_person():
    speaker = SpeakerFactory(name="Alice")
    avail = AvailabilityFactory(event=speaker.event, person=speaker)

    result = str(avail)

    assert (
        result
        == f"Availability(event={speaker.event.slug}, person={speaker.user.get_display_name()}, room=None)"
    )


@pytest.mark.django_db
def test_availability_str_with_room():
    room = RoomFactory(name="Main Hall")
    avail = AvailabilityFactory(event=room.event, room=room)

    result = str(avail)

    assert (
        result
        == f"Availability(event={room.event.slug}, person=None, room={room.name})"
    )


def test_availability_str_without_person_or_room():
    avail = Availability(
        start=dt.datetime(2017, 1, 1, 9), end=dt.datetime(2017, 1, 1, 17)
    )

    result = str(avail)

    assert "person=None" in result
    assert "room=None" in result


def test_availability_hash_depends_on_fields():
    avail1 = _avail(5, 9)
    avail2 = _avail(5, 9)
    avail3 = _avail(5, 10)

    assert hash(avail1) == hash(avail2)
    assert hash(avail1) != hash(avail3)


@pytest.mark.parametrize(
    ("one", "two", "expected"),
    (((5, 9), (5, 9), True), ((5, 9), (5, 10), False)),
    ids=["same_times", "different_times"],
)
def test_availability_eq(one, two, expected):
    assert (_avail(*one) == _avail(*two)) is expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    (
        (dt.datetime(2017, 1, 1, 0, 0), dt.datetime(2017, 1, 2, 0, 0), True),
        (dt.datetime(2017, 1, 1, 9, 0), dt.datetime(2017, 1, 1, 17, 0), False),
    ),
    ids=["spans_full_day", "partial_day"],
)
def test_availability_all_day(start, end, expected):
    avail = Availability(start=start, end=end)

    assert avail.all_day is expected


@pytest.mark.parametrize(
    ("avail_id", "start", "end", "expected"),
    (
        (
            42,
            dt.datetime(2017, 1, 1, 9),
            dt.datetime(2017, 1, 1, 17),
            {
                "id": 42,
                "start": "2017-01-01T09:00:00",
                "end": "2017-01-01T17:00:00",
                "allDay": False,
            },
        ),
        (
            1,
            dt.datetime(2017, 1, 1, 0, 0),
            dt.datetime(2017, 1, 2, 0, 0),
            {
                "id": 1,
                "start": "2017-01-01T00:00:00",
                "end": "2017-01-02T00:00:00",
                "allDay": True,
            },
        ),
    ),
    ids=["partial_day", "all_day"],
)
def test_availability_serialize_full(avail_id, start, end, expected):
    avail = Availability(id=avail_id, start=start, end=end)

    result = avail.serialize(full=True)

    assert result == expected


def test_availability_serialize_minimal():
    avail = Availability(
        start=dt.datetime(2017, 1, 1, 9), end=dt.datetime(2017, 1, 1, 17)
    )

    result = avail.serialize(full=False)

    assert result == {"start": "2017-01-01T09:00:00", "end": "2017-01-01T17:00:00"}


def test_availability_overlaps_raises_for_non_availability():
    avail = _avail(5, 9)

    with pytest.raises(TypeError, match="Availability object"):
        avail.overlaps("not an availability", strict=False)


@pytest.mark.parametrize(
    ("one", "two", "expected_strict", "expected_nonstrict"),
    (
        ((5, 9), (5, 9), True, True),
        ((5, 9), (6, 9), True, True),
        ((5, 9), (7, 10), True, True),
        ((5, 9), (1, 5), False, True),
        ((5, 9), (1, 4), False, False),
        ((9, 16), (10, 15), True, True),
    ),
    ids=[
        "identical",
        "second_inside_first",
        "partial_overlap_right",
        "adjacent_left",
        "no_overlap",
        "contained",
    ],
)
def test_availability_overlaps(one, two, expected_strict, expected_nonstrict):
    a = _avail(*one)
    b = _avail(*two)

    assert a.overlaps(b, strict=True) == expected_strict
    assert b.overlaps(a, strict=True) == expected_strict
    assert a.overlaps(b, strict=False) == expected_nonstrict
    assert b.overlaps(a, strict=False) == expected_nonstrict


@pytest.mark.parametrize(
    ("one", "two", "expected"),
    (
        ((5, 9), (5, 9), True),
        ((5, 9), (6, 9), True),
        ((6, 9), (5, 9), False),
        ((5, 9), (7, 10), False),
        ((5, 9), (1, 5), False),
        ((5, 9), (1, 4), False),
        ((9, 16), (10, 15), True),
    ),
    ids=[
        "identical",
        "second_inside_first",
        "first_inside_second",
        "partial_overlap_right",
        "adjacent_left",
        "no_overlap",
        "contained",
    ],
)
def test_availability_contains(one, two, expected):
    a = _avail(*one)
    b = _avail(*two)

    assert a.contains(b) is expected


@pytest.mark.parametrize(
    ("one", "two", "expected_start", "expected_end"),
    (((4, 7), (5, 9), 4, 9), ((4, 7), (7, 8), 4, 8)),
    ids=["overlapping", "adjacent"],
)
def test_availability_merge_with(one, two, expected_start, expected_end):
    result = _avail(*one).merge_with(_avail(*two))

    assert result.start == dt.datetime(2017, 1, 1, expected_start)
    assert result.end == dt.datetime(2017, 1, 1, expected_end)


def test_availability_merge_with_is_symmetric():
    a = _avail(4, 7)
    b = _avail(5, 9)

    assert a.merge_with(b) == b.merge_with(a)


def test_availability_merge_with_raises_for_non_availability():
    avail = _avail(5, 9)

    with pytest.raises(TypeError, match="Availability object"):
        avail.merge_with("not an availability")


def test_availability_merge_with_raises_for_non_overlapping():
    a = _avail(1, 3)
    b = _avail(5, 9)

    with pytest.raises(ValueError, match="overlap"):
        a.merge_with(b)


def test_availability_or_operator():
    a = _avail(4, 7)
    b = _avail(5, 9)

    result = a | b

    assert result == a.merge_with(b)


@pytest.mark.parametrize(
    ("one", "two", "expected_start", "expected_end"),
    (((4, 7), (5, 9), 5, 7), ((5, 9), (5, 9), 5, 9)),
    ids=["overlapping", "identical"],
)
def test_availability_intersect_with(one, two, expected_start, expected_end):
    result = _avail(*one).intersect_with(_avail(*two))

    assert result.start == dt.datetime(2017, 1, 1, expected_start)
    assert result.end == dt.datetime(2017, 1, 1, expected_end)


def test_availability_intersect_with_is_symmetric():
    a = _avail(4, 7)
    b = _avail(5, 9)

    assert a.intersect_with(b) == b.intersect_with(a)


def test_availability_intersect_with_raises_for_non_availability():
    avail = _avail(5, 9)

    with pytest.raises(TypeError, match="Availability object"):
        avail.intersect_with("not an availability")


def test_availability_intersect_with_raises_for_non_overlapping():
    a = _avail(1, 3)
    b = _avail(5, 9)

    with pytest.raises(ValueError, match="overlap"):
        a.intersect_with(b)


def test_availability_and_operator():
    a = _avail(4, 7)
    b = _avail(5, 9)

    result = a & b

    assert result == a.intersect_with(b)


def test_availability_union_empty():
    assert Availability.union([]) == []


def test_availability_union_single():
    a = _avail(4, 7)

    result = Availability.union([a])

    assert len(result) == 1
    assert result[0].start == a.start
    assert result[0].end == a.end


def test_availability_union_non_overlapping_preserved():
    a = _avail(4, 5)
    b = _avail(6, 7)

    result = Availability.union([a, b])

    assert len(result) == 2
    assert result[0].start == a.start
    assert result[1].start == b.start


def test_availability_union_adjacent_merged():
    a = _avail(4, 5)
    b = _avail(5, 6)

    result = Availability.union([a, b])

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 4)
    assert result[0].end == dt.datetime(2017, 1, 1, 6)


def test_availability_union_overlapping_merged():
    a = _avail(4, 6)
    b = _avail(5, 7)

    result = Availability.union([a, b])

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 4)
    assert result[0].end == dt.datetime(2017, 1, 1, 7)


def test_availability_union_unsorted_input():
    """union sorts by start time before merging."""
    a = _avail(5, 7)
    b = _avail(4, 6)

    result = Availability.union([a, b])

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 4)
    assert result[0].end == dt.datetime(2017, 1, 1, 7)


def test_availability_union_complex():
    """Multiple overlapping groups merge correctly."""
    avails = [
        _avail(10, 12),
        _avail(12, 14),
        _avail(5, 7),
        _avail(6, 8),
        _avail(18, 19),
        _avail(4, 6),
    ]

    result = Availability.union(avails)

    assert len(result) == 3
    assert result[0].start == dt.datetime(2017, 1, 1, 4)
    assert result[0].end == dt.datetime(2017, 1, 1, 8)
    assert result[1].start == dt.datetime(2017, 1, 1, 10)
    assert result[1].end == dt.datetime(2017, 1, 1, 14)
    assert result[2].start == dt.datetime(2017, 1, 1, 18)
    assert result[2].end == dt.datetime(2017, 1, 1, 19)


def test_availability_intersection_empty_sets():
    assert Availability.intersection() == []


def test_availability_intersection_one_set_empty():
    a = [_avail(5, 7)]
    assert Availability.intersection(a, []) == []


def test_availability_intersection_adjacent_no_strict_overlap():
    """Adjacent availabilities don't strictly overlap, so intersection is empty."""
    a = [_avail(5, 7)]
    b = [_avail(7, 9)]

    assert Availability.intersection(a, b) == []


def test_availability_intersection_identical():
    a = [_avail(5, 7)]
    b = [_avail(5, 7)]

    result = Availability.intersection(a, b)

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 5)
    assert result[0].end == dt.datetime(2017, 1, 1, 7)


def test_availability_intersection_partial_overlap():
    a = [_avail(5, 7)]
    b = [_avail(6, 9)]

    result = Availability.intersection(a, b)

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 6)
    assert result[0].end == dt.datetime(2017, 1, 1, 7)


def test_availability_intersection_split_by_gaps():
    """A continuous range intersected with a gapped set produces two ranges."""
    a = [_avail(2, 7)]
    b = [_avail(0, 3), _avail(6, 8)]

    result = Availability.intersection(a, b)

    assert len(result) == 2
    assert result[0].start == dt.datetime(2017, 1, 1, 2)
    assert result[0].end == dt.datetime(2017, 1, 1, 3)
    assert result[1].start == dt.datetime(2017, 1, 1, 6)
    assert result[1].end == dt.datetime(2017, 1, 1, 7)


def test_availability_intersection_three_sets():
    """Three-set intersection passes through inverted ranges (start > end) without validation."""
    a = [_avail(2, 7)]
    b = [_avail(0, 3), _avail(6, 8)]
    c = [_avail(9, 7)]  # start > end: code doesn't validate this

    result = Availability.intersection(a, b, c)

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 9)
    assert result[0].end == dt.datetime(2017, 1, 1, 7)


def test_availability_intersection_is_symmetric():
    a = [_avail(5, 7)]
    b = [_avail(6, 9)]

    result1 = Availability.intersection(a, b)
    result2 = Availability.intersection(b, a)

    assert len(result1) == len(result2)
    for r1, r2 in zip(result1, result2, strict=True):
        assert r1 == r2


def test_availability_intersection_overlapping_within_set():
    """Overlapping availabilities within a single set are unioned first."""
    a = [_avail(2, 7)]
    b = [_avail(0, 3), _avail(3, 4)]

    result = Availability.intersection(a, b)

    assert len(result) == 1
    assert result[0].start == dt.datetime(2017, 1, 1, 2)
    assert result[0].end == dt.datetime(2017, 1, 1, 4)


def test_availability_intersection_multiple_ranges():
    """Complex multi-range intersection across two sets."""
    a = [_avail(2, 7), _avail(10, 12), _avail(14, 19)]
    b = [_avail(0, 3), _avail(6, 8), _avail(13, 15)]

    result = Availability.intersection(a, b)

    assert len(result) == 3
    assert result[0].start == dt.datetime(2017, 1, 1, 2)
    assert result[0].end == dt.datetime(2017, 1, 1, 3)
    assert result[1].start == dt.datetime(2017, 1, 1, 6)
    assert result[1].end == dt.datetime(2017, 1, 1, 7)
    assert result[2].start == dt.datetime(2017, 1, 1, 14)
    assert result[2].end == dt.datetime(2017, 1, 1, 15)


@pytest.mark.django_db
def test_availability_replace_for_instance_replaces_all(event):
    """replace_for_instance deletes existing and bulk-creates new availabilities."""
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)

    new_start = event.datetime_from + dt.timedelta(hours=1)
    new_end = event.datetime_to - dt.timedelta(hours=1)
    new_avails = [Availability(event=event, room=room, start=new_start, end=new_end)]

    with scopes_disabled():
        Availability.replace_for_instance(room, new_avails)
        result = list(room.availabilities.all())

    assert len(result) == 1
    assert result[0].start == new_start
    assert result[0].end == new_end


@pytest.mark.django_db
def test_availability_replace_for_instance_with_person(event):
    """replace_for_instance works for person-based availabilities too."""
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=speaker)

    new_avails = [
        Availability(
            event=event,
            person=speaker,
            start=event.datetime_from,
            end=event.datetime_to,
        )
    ]

    with scopes_disabled():
        Availability.replace_for_instance(speaker, new_avails)
        result = list(speaker.availabilities.all())

    assert len(result) == 1
