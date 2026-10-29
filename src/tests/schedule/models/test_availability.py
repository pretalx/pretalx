# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.models import Availability

pytestmark = pytest.mark.unit


def _avail(start_hour, end_hour, day=1, month=1, year=2017, **kwargs):
    return Availability(
        start=dt.datetime(year, month, day, start_hour),
        end=dt.datetime(year, month, day, end_hour),
        **kwargs,
    )


def _hours(availabilities):
    return [(avail.start.hour, avail.end.hour) for avail in availabilities]


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
    ("avail_id", "start", "end", "full", "expected"),
    (
        (
            42,
            dt.datetime(2017, 1, 1, 9),
            dt.datetime(2017, 1, 1, 17),
            True,
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
            True,
            {
                "id": 1,
                "start": "2017-01-01T00:00:00",
                "end": "2017-01-02T00:00:00",
                "allDay": True,
            },
        ),
        (
            None,
            dt.datetime(2017, 1, 1, 9),
            dt.datetime(2017, 1, 1, 17),
            False,
            {"start": "2017-01-01T09:00:00", "end": "2017-01-01T17:00:00"},
        ),
    ),
    ids=["partial_day", "all_day", "minimal"],
)
def test_availability_serialize(avail_id, start, end, full, expected):
    avail = Availability(id=avail_id, start=start, end=end)

    assert avail.serialize(full=full) == expected


@pytest.mark.parametrize(
    ("method", "kwargs"),
    (("overlaps", {"strict": False}), ("merge_with", {}), ("intersect_with", {})),
)
def test_availability_operations_raise_for_non_availability(method, kwargs):
    avail = _avail(5, 9)

    with pytest.raises(TypeError, match="Availability object"):
        getattr(avail, method)("not an availability", **kwargs)


@pytest.mark.parametrize("method", ("merge_with", "intersect_with"))
def test_availability_operations_raise_for_non_overlapping(method):
    a = _avail(1, 3)
    b = _avail(5, 9)

    with pytest.raises(ValueError, match="overlap"):
        getattr(a, method)(b)


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
    ("one", "two", "expected"),
    (((4, 7), (5, 9), (4, 9)), ((4, 7), (7, 8), (4, 8))),
    ids=["overlapping", "adjacent"],
)
def test_availability_merge_with_is_symmetric(one, two, expected):
    a = _avail(*one)
    b = _avail(*two)

    assert a.merge_with(b) == b.merge_with(a) == (a | b) == _avail(*expected)


@pytest.mark.parametrize(
    ("one", "two", "expected"),
    (((4, 7), (5, 9), (5, 7)), ((5, 9), (5, 9), (5, 9))),
    ids=["overlapping", "identical"],
)
def test_availability_intersect_with_is_symmetric(one, two, expected):
    a = _avail(*one)
    b = _avail(*two)

    assert a.intersect_with(b) == b.intersect_with(a) == (a & b) == _avail(*expected)


@pytest.mark.parametrize(
    ("hours", "expected"),
    (
        ([], []),
        ([(4, 7)], [(4, 7)]),
        ([(4, 5), (6, 7)], [(4, 5), (6, 7)]),
        ([(4, 5), (5, 6)], [(4, 6)]),
        ([(4, 6), (5, 7)], [(4, 7)]),
        ([(5, 7), (4, 6)], [(4, 7)]),
        (
            [(10, 12), (12, 14), (5, 7), (6, 8), (18, 19), (4, 6)],
            [(4, 8), (10, 14), (18, 19)],
        ),
    ),
    ids=[
        "empty",
        "single",
        "non_overlapping_preserved",
        "adjacent_merged",
        "overlapping_merged",
        "unsorted_input",
        "complex",
    ],
)
def test_availability_union(hours, expected):
    result = Availability.union([_avail(*pair) for pair in hours])

    assert _hours(result) == expected


@pytest.mark.parametrize(
    ("sets", "expected"),
    (
        ([], []),
        ([[(5, 7)], []], []),
        ([[(5, 7)], [(7, 9)]], []),
        ([[(5, 7)], [(5, 7)]], [(5, 7)]),
        ([[(5, 7)], [(6, 9)]], [(6, 7)]),
        ([[(6, 9)], [(5, 7)]], [(6, 7)]),
        ([[(2, 7)], [(0, 3), (6, 8)]], [(2, 3), (6, 7)]),
        (
            [[(2, 7)], [(0, 3), (6, 8)], [(9, 7)]],
            [(9, 7)],
        ),  # start > end: not validated
        ([[(2, 7)], [(0, 3), (3, 4)]], [(2, 4)]),
        (
            [[(2, 7), (10, 12), (14, 19)], [(0, 3), (6, 8), (13, 15)]],
            [(2, 3), (6, 7), (14, 15)],
        ),
    ),
    ids=[
        "no_sets",
        "one_set_empty",
        "adjacent_no_strict_overlap",
        "identical",
        "partial_overlap",
        "partial_overlap_swapped",
        "split_by_gaps",
        "three_sets",
        "overlapping_within_set",
        "multiple_ranges",
    ],
)
def test_availability_intersection(sets, expected):
    result = Availability.intersection(
        *([_avail(*pair) for pair in hours] for hours in sets)
    )

    assert _hours(result) == expected
