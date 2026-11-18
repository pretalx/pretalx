import datetime as dt

from pretalx_track_schedule.layout import (
    Break,
    Session,
    assign_lanes,
    dedupe_breaks,
    layout_day,
)

DAY = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)


def at(hour, minute=0):
    return DAY.replace(hour=hour, minute=minute)


def session(start, end, track="A"):
    return Session(start=start, end=end, track=track)


def test_overlapping_sessions_get_separate_lanes():
    first, second = session(at(10), at(11)), session(at(10, 30), at(11, 30))
    placed, lanes = assign_lanes([first, second])
    assert lanes == 2
    assert {id(s): lane for s, lane in placed} == {id(first): 0, id(second): 1}


def test_back_to_back_sessions_share_a_lane():
    placed, lanes = assign_lanes([session(at(10), at(11)), session(at(11), at(12))])
    assert lanes == 1
    assert [lane for _, lane in placed] == [0, 0]


def test_freed_lane_is_reused_lowest_first():
    sessions = [
        session(at(10), at(11)),  # lane 0
        session(at(10), at(12)),  # lane 1
        session(at(10), at(13)),  # lane 2
        session(at(11), at(12)),  # lane 0 is free again
    ]
    placed, lanes = assign_lanes(sessions)
    assert lanes == 3
    assert [lane for _, lane in placed] == [0, 1, 2, 0]


def test_same_time_same_track_side_by_side_in_grid():
    first, second = session(at(10), at(11)), session(at(10), at(11))
    layout = layout_day([first, second], [], ["A"])
    track = layout.tracks[0]
    assert track.lanes == 2
    columns = {placed.column for placed in layout.sessions}
    assert columns == {2, 3}
    rows = {(placed.row_start, placed.row_end) for placed in layout.sessions}
    assert len(rows) == 1


def test_break_in_several_rooms_rendered_once_across_columns():
    breaks = [Break(start=at(12), end=at(13), description="Lunch") for _ in range(3)]
    layout = layout_day(
        [session(at(10), at(11), "A"), session(at(10), at(11), "B")], breaks, ["A", "B"]
    )
    assert len(layout.breaks) == 1
    assert layout.breaks[0].column == 2
    assert layout.end_column == 4  # spans grid lines 2 to 4: both tracks


def test_dedupe_keeps_different_breaks():
    breaks = [
        Break(start=at(12), end=at(13), description="Lunch"),
        Break(start=at(12), end=at(13), description="Lunch"),
        Break(start=at(15), end=at(15, 30), description="Coffee"),
        Break(start=at(12), end=at(13), description="Quiet lunch"),
    ]
    assert len(dedupe_breaks(breaks)) == 3


def test_sessions_without_track_go_last_in_no_track_column():
    layout = layout_day(
        [session(at(10), at(11), None), session(at(10), at(11), "B")], [], ["A", "B"]
    )
    assert [t.track for t in layout.tracks] == ["B", None]


def test_track_order_and_lane_columns():
    layout = layout_day(
        [
            session(at(10), at(11), "B"),
            session(at(10), at(11), "A"),
            session(at(10), at(11), "A"),
        ],
        [],
        ["A", "B"],
    )
    assert [(t.track, t.column, t.lanes) for t in layout.tracks] == [
        ("A", 2, 2),
        ("B", 4, 1),
    ]
    assert layout.lanes == 3


def test_rows_are_slices_from_first_start():
    layout = layout_day([session(at(10, 2), at(10, 30))], [], ["A"], slice_minutes=5)
    placed = layout.sessions[0]
    # Day starts at 10:00 (floored); header is row 1, 10:00 is row 2
    assert (placed.row_start, placed.row_end) == (2, 8)
    assert layout.slices == 6
    assert layout.labels == [(2, at(10))]


def test_zero_length_session_gets_a_row():
    layout = layout_day([session(at(10), at(10))], [], ["A"])
    placed = layout.sessions[0]
    assert placed.row_end == placed.row_start + 1


def test_list_agenda_interleaves_breaks_by_time():
    layout = layout_day(
        [session(at(10), at(11)), session(at(13), at(14))],
        [Break(start=at(12), end=at(13), description="Lunch")],
        ["A"],
    )
    kinds = [placed.item.is_break for placed in layout.tracks[0].agenda]
    assert kinds == [False, True, False]


def test_empty_day():
    layout = layout_day([], [], ["A"])
    assert layout.tracks == [] and layout.slices == 0
