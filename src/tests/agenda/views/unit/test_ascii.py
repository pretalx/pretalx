# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import re

import pytest

from pretalx.agenda.views.ascii import (
    draw_ascii_schedule,
    draw_grid_for_day,
    draw_schedule_grid,
    draw_schedule_list,
    get_line_parts,
    talk_card,
)
from pretalx.schedule.models import TalkSlot
from tests.factories import (
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

START = dt.datetime(2024, 1, 15, 10, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _disable_scopes():
    return


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text):
    return ANSI_RE.sub("", text)


def _talk(
    title="Talk Title",
    speakers="Speaker Name",
    locale="en",
    room_name="Room 1",
    start=None,
    duration=30,
    has_submission=True,
    description="Break",
):
    if start is None:
        start = START
    end = start + dt.timedelta(minutes=duration)

    event = EventFactory()
    room = RoomFactory(event=event, name=room_name)

    submission = None
    if has_submission:
        submission = SubmissionFactory(event=event, title=title, content_locale=locale)
        if speakers:
            user = UserFactory(name=speakers)
            speaker = SpeakerFactory(event=event, user=user)
            submission.speakers.add(speaker)

    slot_kwargs = {
        "submission": submission,
        "room": room,
        "start": start,
        "end": end,
        "description": description,
    }
    if not has_submission:
        slot_kwargs["schedule"] = event.wip_schedule

    slot = TalkSlotFactory(**slot_kwargs)
    return (
        TalkSlot.objects.select_related("submission__event", "room", "schedule__event")
        .with_sorted_speakers()
        .get(pk=slot.pk)
    )


EMPTY_DAY = {"start": START, "rooms": [{"name": "Room 1", "talks": []}]}


@pytest.mark.parametrize("data", ([], [EMPTY_DAY]), ids=["no_days", "no_talks"])
def test_draw_schedule_list_empty_without_talks(data):
    assert draw_schedule_list(data) == ""


def test_draw_schedule_list_renders_days_and_talks_in_start_order():
    early = _talk(title="Early", speakers="", room_name="Main Hall")
    lunch = _talk(
        has_submission=False,
        description="Lunch Break",
        room_name="Foyer",
        start=START + dt.timedelta(minutes=5),
    )
    late = _talk(
        title="Late",
        speakers="Alice",
        locale="de",
        room_name="Main Hall",
        start=START + dt.timedelta(hours=1),
    )
    day2_start = START + dt.timedelta(days=1)
    day2_talk = _talk(title="Day2 Talk", room_name="R", start=day2_start)
    data = [
        {
            "start": START,
            "rooms": [
                {"name": "Main Hall", "talks": [late, early]},
                {"name": "Foyer", "talks": [lunch]},
            ],
        },
        {"start": day2_start, "rooms": [{"name": "R", "talks": [day2_talk]}]},
    ]

    result = _strip_ansi(draw_schedule_list(data))

    assert result == (
        "\n2024-01-15\n"
        "* 10:00 Early, No speakers (en); in Main Hall\n"
        "* 10:05 Lunch Break in Foyer\n"
        "* 11:00 Late, Alice (de); in Main Hall\n"
        "\n2024-01-16\n"
        "* 10:00 Day2 Talk, Speaker Name (en); in R\n"
    )


@pytest.mark.parametrize(
    ("talk_kwargs", "expected_lines"),
    (
        (
            {
                "title": "This is a very long title that exceeds the column width",
                "speakers": "Alice",
                "locale": "de",
                "duration": 15,
            },
            ["  This is a very …  ", "  Alice         de  ", "                    "],
        ),
        (
            {"duration": 30},
            [
                "                    ",
                "  Talk Title        ",
                "                    ",
                "  Speaker Name      ",
                "                en  ",
                "                    ",
            ],
        ),
        (
            {"speakers": "A" * 50, "duration": 60},
            [
                "                    ",
                "  Talk Title        ",
                "                    ",
                "  AAAAAAAAAAAAAAA…  ",
                "                    ",
                "                en  ",
                *["                    "] * 6,
            ],
        ),
        (
            {"speakers": "", "duration": 30},
            [
                "                    ",
                "  Talk Title        ",
                "                    ",
                "                en  ",
                "                    ",
                "                    ",
            ],
        ),
        (
            {"has_submission": False, "description": "Coffee Break", "duration": 30},
            [
                "                    ",
                "  Coffee Break      ",
                *["                    "] * 4,
            ],
        ),
    ),
    ids=[
        "short_card_truncates_title_and_joins_speaker_with_locale",
        "medium_card_separates_speaker_and_locale",
        "tall_card_truncates_speaker",
        "no_speakers_still_shows_locale",
        "break_shows_description_only",
    ],
)
def test_talk_card_fills_card_height(talk_kwargs, expected_lines):
    talk = _talk(**talk_kwargs)

    lines = [_strip_ansi(line) for line in talk_card(talk, col_width=20)]

    assert lines == expected_lines
    assert len(lines) == talk.duration // 5


@pytest.mark.parametrize(
    ("start1", "start2", "end1", "end2", "run1", "run2", "fill_char", "expected"),
    (
        # run1 + start/end on other side → ├
        (None, True, None, None, True, None, " ", "├"),
        (None, None, None, True, True, None, " ", "├"),
        # run2 + start/end on other side → ┤
        (True, None, None, None, None, True, " ", "┤"),
        (None, None, True, None, None, True, " ", "┤"),
        # Only starts/ends (no runs) → get_separator result
        (True, None, None, None, None, None, " ", "┐"),
        (True, True, None, None, None, None, " ", "┬"),
        (None, None, True, True, None, None, " ", "┴"),
        # Both running → │
        (None, None, None, None, True, True, " ", "│"),
        # Nothing → fill_char
        (None, None, None, None, None, None, "-", "-"),
    ),
    ids=[
        "run1_and_start2",
        "run1_and_end2",
        "run2_and_start1",
        "run2_and_end1",
        "start1_only",
        "both_starting",
        "both_ending",
        "both_running",
        "nothing",
    ],
)
def test_get_line_parts(start1, start2, end1, end2, run1, run2, fill_char, expected):
    result = get_line_parts(
        start1=start1,
        start2=start2,
        end1=end1,
        end2=end2,
        run1=run1,
        run2=run2,
        fill_char=fill_char,
    )
    assert result == [expected]


def test_draw_grid_for_day_no_talks_returns_none():
    assert draw_grid_for_day(EMPTY_DAY) is None


@pytest.mark.parametrize(
    ("short_room", "long_room"),
    (("Room 1", "Room 2"), ("Room 2", "Room 1")),
    ids=["first_room_ends_early", "last_room_ends_early"],
)
def test_draw_grid_for_day_renders_rooms_talks_and_breaks(short_room, long_room):
    short = _talk(title="Short", room_name=short_room, duration=15)
    long_ = _talk(
        has_submission=False, description="Coffee", room_name=long_room, duration=30
    )
    day = {
        "rooms": [
            {"name": "Room 1", "talks": [short if short_room == "Room 1" else long_]},
            {"name": "Room 2", "talks": [short if short_room == "Room 2" else long_]},
        ]
    }

    plain = _strip_ansi(draw_grid_for_day(day, col_width=20))

    assert "Room 1" in plain
    assert "Room 2" in plain
    assert "10:00" in plain
    assert "10:30" in plain
    assert "Short" in plain
    assert "Coffee" in plain


def test_draw_schedule_grid_day_without_talks():
    assert "No talks on this day." in draw_schedule_grid([EMPTY_DAY])
    assert draw_ascii_schedule([EMPTY_DAY]) == draw_schedule_grid([EMPTY_DAY])


def test_draw_schedule_grid_day_with_talks_and_custom_col_width():
    talk = _talk(duration=30)
    day = {
        "start": START,
        "rooms": [{"name": "Room 1", "talks": [talk]}],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = _strip_ansi(draw_schedule_grid([day], col_width=30))

    assert "2024-01-15" in result
    assert "Talk Title" in result
    assert "Room 1" in result
    assert result.splitlines()[2] == "        | " + "Room 1".ljust(28)


@pytest.mark.parametrize("output_format", ("list", "table"))
def test_draw_ascii_schedule_strips_control_characters(output_format):
    # terminal escape starts: \x1b is ESC and \x9b is the 8-bit CSI
    title = "Talk\x1b[31m\x9btitle"
    room_name = "Roo\x9bm"
    talk = _talk(title=title, room_name=room_name, duration=30)
    data = [
        {
            "start": START,
            "rooms": [{"name": room_name, "talks": [talk]}],
            "first_start": START,
            "last_end": START + dt.timedelta(minutes=30),
        }
    ]

    result = draw_ascii_schedule(data, output_format=output_format)

    assert "\x9b" not in result
    assert "Talk[31mtitle" in _strip_ansi(result)
