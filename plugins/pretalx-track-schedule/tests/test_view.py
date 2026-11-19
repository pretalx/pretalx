import re

import pytest


def _url(event):
    return f"/{event.slug}/p/track-schedule/"


def _get(client, url):
    # Like a browser: the built-in schedule answers non-HTML clients with text
    return client.get(url, HTTP_ACCEPT="text/html")


@pytest.fixture
def tracks(event):
    from pretalx.submission.models import Track

    return {
        "second": Track.objects.create(
            event=event, name="Staff Training", color="#00aa00", position=2
        ),
        "first": Track.objects.create(
            event=event, name="General", color="#aa0000", position=1
        ),
    }


def test_released_schedule_by_track(
    event, rooms, tracks, at, schedule_slot, add_break, release, speaker, client_for
):
    # Same track, same time, different rooms: side by side
    schedule_slot("Alpha", rooms[0], at(10), at(11), tracks["first"], (speaker,))
    schedule_slot("Beta", rooms[1], at(10), at(11), tracks["first"])
    schedule_slot("Gamma", rooms[2], at(10), at(11), tracks["second"])
    schedule_slot("Untracked", rooms[2], at(11), at(12))
    for room in rooms:
        add_break(room, at(12), at(13), "Lunch")
    release()

    response = _get(client_for(), _url(event))
    assert response.status_code == 200
    html = response.content.decode()

    for text in ("Alpha", "Beta", "Gamma", "Untracked", "Room 1", "Speaker"):
        assert text in html
    # Track order by position, then "No track"
    assert html.index("General") < html.index("Staff Training") < html.index("No track")
    # Grid placement, from the layout the template rendered
    ((day, layout),) = response.context["days"]
    placed = {p.item.data.submission.title: p for p in layout.sessions}
    assert {t: placed[t].column for t in placed} == {
        "Alpha": 2,
        "Beta": 3,
        "Gamma": 4,
        "Untracked": 5,
    }
    assert (placed["Alpha"].row_start, placed["Alpha"].row_end) == (
        placed["Beta"].row_start,
        placed["Beta"].row_end,
    )
    # The lunch exists in three rooms but is laid out once, across all tracks
    assert len(layout.breaks) == 1
    assert (layout.breaks[0].column, layout.end_column) == (2, 6)
    # Session links go to the normal session pages
    proposal = event.submissions.get(title="Alpha")
    assert str(proposal.urls.public) in html


def test_hidden_without_released_schedule(event, rooms, at, schedule_slot, client_for):
    schedule_slot("Alpha", rooms[0], at(10), at(11))
    assert _get(client_for(), _url(event)).status_code == 404


def test_hidden_when_schedule_feature_off(
    event, rooms, at, schedule_slot, release, client_for
):
    schedule_slot("Alpha", rooms[0], at(10), at(11))
    release()
    event.feature_flags["show_schedule"] = False
    event.save()
    assert _get(client_for(), _url(event)).status_code == 404
    assert _get(client_for(), f"/{event.slug}/schedule/").status_code != 200


def test_hidden_for_non_public_event(
    event, rooms, at, schedule_slot, release, client_for
):
    schedule_slot("Alpha", rooms[0], at(10), at(11))
    release()
    event.is_public = False
    event.save()
    assert _get(client_for(), _url(event)).status_code == 404


def test_hidden_without_plugin(event, rooms, at, schedule_slot, release, client_for):
    from pretalx.event.domain.plugins import disable_plugin

    schedule_slot("Alpha", rooms[0], at(10), at(11))
    release()
    disable_plugin(event, "pretalx_track_schedule")
    assert _get(client_for(), _url(event)).status_code == 404


def test_footer_link(event, rooms, at, schedule_slot, release, client_for):
    client = client_for()
    assert _url(event) not in _get(client, f"/{event.slug}/").content.decode()
    schedule_slot("Alpha", rooms[0], at(10), at(11))
    release()
    html = _get(client, f"/{event.slug}/schedule/").content.decode()
    assert _url(event) in html


def test_one_section_per_day(event, rooms, at, schedule_slot, release, client_for):
    import datetime as dt

    event.date_to = event.date_from + dt.timedelta(days=1)
    event.save()
    schedule_slot("Day one", rooms[0], at(10), at(11))
    schedule_slot(
        "Day two",
        rooms[0],
        at(10) + dt.timedelta(days=1),
        at(11) + dt.timedelta(days=1),
    )
    release()
    html = _get(client_for(), _url(event)).content.decode()
    assert len(re.findall(r'class="?ts-day"? id="?day-', html)) == 2
    assert f"#day-{event.date_from.isoformat()}" in html


def test_header_tab_script_on_schedule_pages(
    event, rooms, at, schedule_slot, release, client_for
):
    client = client_for()
    schedule_slot("Alpha", rooms[0], at(10), at(11))
    # Not before the schedule is released
    assert (
        "track-schedule-tab"
        not in _get(client, f"/{event.slug}/talk/").content.decode()
    )
    release()
    for page in ("schedule/", "talk/", "speaker/", "p/track-schedule/"):
        html = _get(client, f"/{event.slug}/{page}").content.decode()
        assert "pretalx_track_schedule/tab.js" in html, page
        assert _url(event) in html, page
    # Not on CfP pages, which have no schedule tabs
    html = _get(client, f"/{event.slug}/cfp").content.decode()
    assert "track-schedule-tab" not in html
