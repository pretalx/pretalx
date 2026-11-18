"""Grid maths for one day of the track schedule. Pure: no Django, no database,
so it can be tested on plain values.

The day is a CSS grid. Row 1 holds the track headers; each further row is one
time slice. Column 1 holds the time labels; then each track gets one column per
lane, so sessions of a track that overlap in time sit side by side.
"""

import datetime as dt
import heapq
from dataclasses import dataclass, field
from typing import Any

SLICE_MINUTES = 5
LABEL_EVERY_MINUTES = 30
HEADER_ROWS = 1
FIRST_TRACK_COLUMN = 2


@dataclass
class Session:
    start: dt.datetime
    end: dt.datetime
    # Any hashable identifying the track; None is "no track"
    track: Any
    data: Any = None
    is_break = False


@dataclass
class Break:
    start: dt.datetime
    end: dt.datetime
    description: str
    data: Any = None
    is_break = True


@dataclass
class Placed:
    item: Any
    column: int
    row_start: int
    row_end: int


@dataclass
class TrackColumn:
    track: Any
    column: int
    lanes: int
    sessions: list = field(default_factory=list)
    # Sessions and breaks in time order, for the narrow-screen list
    agenda: list = field(default_factory=list)


@dataclass
class DayLayout:
    tracks: list
    sessions: list
    breaks: list
    labels: list
    # Grid line after the last track column (breaks span 2 to this)
    end_column: int
    # Track columns (all lanes) and time-slice rows, without the label
    # column and header row
    lanes: int
    slices: int


def assign_lanes(sessions):
    """Puts each session in the first (lowest) lane that is free at its start:
    a lane is free once its last session ended at or before that start, so
    back-to-back sessions share a lane. Returns ([(session, lane)], lane count),
    in start order. O(n log n)."""
    placed = []
    busy = []  # (end, lane) of lanes in use
    free = []  # lane numbers that are free again
    lanes = 0
    for session in sorted(sessions, key=lambda s: (s.start, s.end)):
        while busy and busy[0][0] <= session.start:
            heapq.heappush(free, heapq.heappop(busy)[1])
        if free:
            lane = heapq.heappop(free)
        else:
            lane = lanes
            lanes += 1
        heapq.heappush(busy, (session.end, lane))
        placed.append((session, lane))
    return placed, lanes


def dedupe_breaks(breaks):
    """Breaks are stored once per room; keep one per (start, end, description)."""
    seen = set()
    result = []
    for item in sorted(breaks, key=lambda b: (b.start, b.end, b.description)):
        key = (item.start, item.end, item.description)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _floor(moment, minutes):
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    offset = (moment - midnight) // dt.timedelta(minutes=minutes)
    return midnight + offset * dt.timedelta(minutes=minutes)


def _ceil(moment, minutes):
    floored = _floor(moment, minutes)
    return floored if floored == moment else floored + dt.timedelta(minutes=minutes)


def layout_day(sessions, breaks, track_order, slice_minutes=SLICE_MINUTES):
    """Lays out one day. ``track_order`` lists the tracks in display order;
    only tracks with sessions get a column, and sessions whose track is None
    (or not in ``track_order``) go in a last "no track" column, with track None.
    """
    breaks = dedupe_breaks(breaks)
    items = [*sessions, *breaks]
    if not items:
        return DayLayout(
            tracks=[],
            sessions=[],
            breaks=[],
            labels=[],
            end_column=2,
            lanes=0,
            slices=0,
        )
    slice_ = dt.timedelta(minutes=slice_minutes)
    day_start = _floor(min(i.start for i in items), slice_minutes)
    day_end = _ceil(max(max(i.end, i.start + slice_) for i in items), slice_minutes)

    def row(moment):
        return HEADER_ROWS + 1 + (moment - day_start) // slice_

    def rows_for(item):
        start = row(_floor(item.start, slice_minutes))
        # Zero-length or sub-slice items still get one row
        end = max(row(_ceil(item.end, slice_minutes)), start + 1)
        return start, end

    known = set(track_order)
    by_track = {}
    for session in sessions:
        key = session.track if session.track in known else None
        by_track.setdefault(key, []).append(session)
    ordered = [t for t in track_order if t in by_track]
    if None in by_track:
        ordered.append(None)

    tracks, placed_sessions = [], []
    column = FIRST_TRACK_COLUMN
    for track in ordered:
        lanes_placed, lanes = assign_lanes(by_track[track])
        track_column = TrackColumn(track=track, column=column, lanes=lanes)
        for session, lane in lanes_placed:
            start, end = rows_for(session)
            placed = Placed(session, column + lane, start, end)
            track_column.sessions.append(placed)
            placed_sessions.append(placed)
        tracks.append(track_column)
        column += lanes

    placed_breaks = [
        Placed(item, FIRST_TRACK_COLUMN, *rows_for(item)) for item in breaks
    ]
    for track_column in tracks:
        track_column.agenda = sorted(
            [*track_column.sessions, *placed_breaks],
            key=lambda placed: (placed.item.start, isinstance(placed.item, Session)),
        )

    labels = []
    moment = _ceil(day_start, LABEL_EVERY_MINUTES)
    while moment < day_end:
        labels.append((row(moment), moment))
        moment += dt.timedelta(minutes=LABEL_EVERY_MINUTES)

    return DayLayout(
        tracks=tracks,
        sessions=placed_sessions,
        breaks=placed_breaks,
        labels=labels,
        end_column=column,
        lanes=column - FIRST_TRACK_COLUMN,
        slices=(day_end - day_start) // slice_,
    )
