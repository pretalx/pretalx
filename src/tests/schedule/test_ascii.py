import datetime as dt
import re

import pytest
from django_scopes import scopes_disabled

from pretalx.schedule.ascii import (
    draw_ascii_schedule,
    draw_grid_for_day,
    draw_schedule_grid,
    draw_schedule_list,
    get_line_parts,
    talk_card,
)
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
    with scopes_disabled():
        yield


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
    """Build a TalkSlot with real DB objects for the ascii renderer tests."""
    if start is None:
        start = START
    end = start + dt.timedelta(minutes=duration)

    with scopes_disabled():
        event = EventFactory()
        room = RoomFactory(event=event, name=room_name)

        submission = None
        if has_submission:
            submission = SubmissionFactory(
                event=event, title=title, content_locale=locale
            )
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

        return TalkSlotFactory(**slot_kwargs)


def test_draw_schedule_list_empty_data():
    assert draw_schedule_list([]) == ""


def test_draw_schedule_list_day_with_no_talks():
    data = [{"start": START, "rooms": [{"name": "Room 1", "talks": []}]}]
    assert draw_schedule_list(data) == ""


def test_draw_schedule_list_talk_with_submission():
    talk = _talk(title="My Talk", speakers="Alice", locale="de", room_name="Main Hall")
    data = [{"start": START, "rooms": [{"name": "Main Hall", "talks": [talk]}]}]

    result = _strip_ansi(draw_schedule_list(data))

    assert "2024-01-15" in result
    assert "10:00" in result
    assert "My Talk" in result
    assert "Alice" in result
    assert "(de)" in result
    assert "Main Hall" in result


def test_draw_schedule_list_talk_without_submission():
    talk = _talk(has_submission=False, description="Lunch Break", room_name="Foyer")
    data = [{"start": START, "rooms": [{"name": "Foyer", "talks": [talk]}]}]

    result = _strip_ansi(draw_schedule_list(data))

    assert "Lunch Break" in result
    assert "Foyer" in result


def test_draw_schedule_list_talk_without_speakers():
    """Talks with no speakers show a 'No speakers' fallback."""
    talk = _talk(speakers="")
    data = [{"start": START, "rooms": [{"name": "Room 1", "talks": [talk]}]}]

    result = _strip_ansi(draw_schedule_list(data))

    assert "No speakers" in result


def test_draw_schedule_list_sorts_talks_by_start_time():
    early = _talk(title="Early", start=START)
    late = _talk(title="Late", start=START + dt.timedelta(hours=1))
    data = [{"start": START, "rooms": [{"name": "Room", "talks": [late, early]}]}]

    result = _strip_ansi(draw_schedule_list(data))

    assert result.index("Early") < result.index("Late")


def test_draw_schedule_list_multiple_rooms():
    talk1 = _talk(title="Talk A", room_name="Room 1")
    talk2 = _talk(
        title="Talk B", room_name="Room 2", start=START + dt.timedelta(minutes=5)
    )
    data = [
        {
            "start": START,
            "rooms": [
                {"name": "Room 1", "talks": [talk1]},
                {"name": "Room 2", "talks": [talk2]},
            ],
        }
    ]

    result = _strip_ansi(draw_schedule_list(data))

    assert "Talk A" in result
    assert "Talk B" in result


def test_draw_schedule_list_multiple_days():
    day1_talk = _talk(title="Day1 Talk")
    day2_start = START + dt.timedelta(days=1)
    day2_talk = _talk(title="Day2 Talk", start=day2_start)
    data = [
        {"start": START, "rooms": [{"name": "R", "talks": [day1_talk]}]},
        {"start": day2_start, "rooms": [{"name": "R", "talks": [day2_talk]}]},
    ]

    result = _strip_ansi(draw_schedule_list(data))

    assert "2024-01-15" in result
    assert "2024-01-16" in result
    assert "Day1 Talk" in result
    assert "Day2 Talk" in result


def test_talk_card_yields_correct_line_count():
    """talk_card yields exactly duration // 5 lines for standard durations."""
    talk = _talk(duration=30)  # height = 5, yields 6 lines
    lines = list(talk_card(talk, col_width=20))
    assert len(lines) == 6


def test_talk_card_short_talk_includes_title():
    talk = _talk(title="Short", duration=15)
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "Short" in text


def test_talk_card_includes_speaker_and_locale():
    talk = _talk(speakers="Alice", locale="de", duration=30)
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "Alice" in text
    assert "de" in text


def test_talk_card_without_submission_shows_description():
    talk = _talk(has_submission=False, description="Coffee Break", duration=30)
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "Coffee Break" in text


def test_talk_card_long_title_truncated():
    """A title too long for available lines gets truncated with ellipsis."""
    long_title = "This is a very long title that definitely exceeds the column width"
    talk = _talk(title=long_title, duration=15)  # height=2, max_title_lines=1
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "…" in text


def test_talk_card_long_speaker_name_truncated():
    long_speaker = "A" * 50
    talk = _talk(speakers=long_speaker, duration=30)
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "…" in text


def test_talk_card_empty_speaker_still_shows_locale():
    """A talk with submission but empty speaker name still shows locale."""
    talk = _talk(speakers="", duration=30)
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "en" in text


def test_talk_card_tall_card_separates_speaker_and_locale():
    """With height > 5, speaker and locale are on separate lines."""
    talk = _talk(duration=60)  # height=11, height_after_title > 3
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "Speaker Name" in text
    assert "en" in text


def test_talk_card_joined_speaker_and_locale():
    """With short height, speaker and locale are on the same line."""
    talk = _talk(duration=15)  # height=2, height_after_title <= 3
    lines = list(talk_card(talk, col_width=20))
    text = _strip_ansi("\n".join(lines))
    assert "Speaker Name" in text
    assert "en" in text


def test_talk_card_all_lines_match_col_width():
    talk = _talk(duration=30)
    col_width = 20
    for line in talk_card(talk, col_width):
        stripped = _strip_ansi(line)
        assert len(stripped) == col_width


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
    day = {"start": START, "rooms": [{"name": "Room 1", "talks": []}]}
    assert draw_grid_for_day(day) is None


def test_draw_grid_for_day_single_talk():
    talk = _talk(title="My Talk", duration=30, start=START, room_name="Room 1")
    day = {
        "start": START,
        "rooms": [{"name": "Room 1", "talks": [talk]}],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = draw_grid_for_day(day, col_width=20)

    assert result is not None
    plain = _strip_ansi(result)
    assert "Room 1" in plain
    assert "10:00" in plain
    assert "My Talk" in plain


def test_draw_grid_for_day_two_rooms():
    talk1 = _talk(title="Talk A", room_name="Room 1", duration=30)
    talk2 = _talk(title="Talk B", room_name="Room 2", duration=30)
    day = {
        "start": START,
        "rooms": [
            {"name": "Room 1", "talks": [talk1]},
            {"name": "Room 2", "talks": [talk2]},
        ],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = draw_grid_for_day(day, col_width=20)
    plain = _strip_ansi(result)

    assert "Room 1" in plain
    assert "Room 2" in plain
    assert "Talk A" in plain
    assert "Talk B" in plain


def test_draw_grid_for_day_derives_start_end_from_talks():
    """When first_start/last_end are not in the day dict, they are derived from talks."""
    talk = _talk(duration=30, start=START)
    day = {"rooms": [{"name": "Room 1", "talks": [talk]}]}

    result = draw_grid_for_day(day, col_width=20)

    assert result is not None
    assert "10:00" in _strip_ansi(result)


def test_draw_grid_for_day_break_without_submission():
    talk = _talk(
        has_submission=False, description="Coffee", duration=30, room_name="Foyer"
    )
    day = {
        "start": START,
        "rooms": [{"name": "Foyer", "talks": [talk]}],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = draw_grid_for_day(day, col_width=20)

    assert result is not None
    assert "Coffee" in _strip_ansi(result)


def test_draw_schedule_grid_day_without_talks():
    day = {"start": START, "rooms": [{"name": "Room 1", "talks": []}]}
    result = draw_schedule_grid([day])
    assert "No talks on this day." in result


def test_draw_schedule_grid_day_with_talks():
    talk = _talk(duration=30)
    day = {
        "start": START,
        "rooms": [{"name": "Room 1", "talks": [talk]}],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = _strip_ansi(draw_schedule_grid([day]))

    assert "2024-01-15" in result
    assert "Talk Title" in result


def test_draw_schedule_grid_custom_col_width():
    talk = _talk(duration=30)
    day = {
        "start": START,
        "rooms": [{"name": "Room 1", "talks": [talk]}],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = _strip_ansi(draw_schedule_grid([day], col_width=30))

    assert "Talk Title" in result
    assert "Room 1" in result


@pytest.mark.parametrize("output_format", ("list", "table"))
def test_draw_ascii_schedule_renders_talk(output_format):
    talk = _talk(duration=30)
    data = [
        {
            "start": START,
            "rooms": [{"name": "Room 1", "talks": [talk]}],
            "first_start": START,
            "last_end": START + dt.timedelta(minutes=30),
        }
    ]

    result = draw_ascii_schedule(data, output_format=output_format)

    assert "Talk Title" in _strip_ansi(result)


@pytest.mark.parametrize(
    ("short_room", "long_room"),
    (("Room 1", "Room 2"), ("Room 2", "Room 1")),
    ids=["first_room_short", "last_room_short"],
)
def test_draw_grid_for_day_room_empty_at_end(short_room, long_room):
    """When one room's talk ends before the grid ends, empty lines are drawn."""
    short = _talk(title="Short", room_name=short_room, duration=15)
    long_ = _talk(title="Long", room_name=long_room, duration=30)
    day = {
        "start": START,
        "rooms": [
            {"name": "Room 1", "talks": [short if short_room == "Room 1" else long_]},
            {"name": "Room 2", "talks": [short if short_room == "Room 2" else long_]},
        ],
        "first_start": START,
        "last_end": START + dt.timedelta(minutes=30),
    }

    result = draw_grid_for_day(day, col_width=20)
    plain = _strip_ansi(result)

    assert "Short" in plain
    assert "Long" in plain


def test_draw_ascii_schedule_default_is_table():
    talk = _talk(duration=30)
    data = [
        {
            "start": START,
            "rooms": [{"name": "Room 1", "talks": [talk]}],
            "first_start": START,
            "last_end": START + dt.timedelta(minutes=30),
        }
    ]

    result_default = draw_ascii_schedule(data)
    result_table = draw_ascii_schedule(data, output_format="table")

    assert result_default == result_table
