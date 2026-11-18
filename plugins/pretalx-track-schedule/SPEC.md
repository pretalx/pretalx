# pretalx-track-schedule: spec

Status: implemented (see README.md). The notes below are the original spec.

## Goal

A public, read-only schedule page that uses **tracks** as columns instead of
rooms. The built-in schedule (`/<event>/schedule/`) stays unchanged.

Why a plugin: the image installs pretalx from PyPI (`PRETALX_VERSION` in
`/Dockerfile`), so edits to `src/pretalx/frontend/` never reach production.

## Scope

In:
- URL `/<event>/p/track-schedule/`, server-rendered (Django template + CSS,
  no JS build step).
- One tab or section per day, in the event timezone.
- One column per track that has sessions that day, ordered by
  `Track.position`, then a "No track" column if needed.
- Track colour on column headers and session cards (`Track.color`).
- Card: start–end time, title (links to the normal session page,
  `submission.urls.public`), speakers, **room name**.
- Breaks span all columns.
- Lanes for sessions in the same track that overlap in time (see Layout).
- Narrow screens: fall back to a list per track (CSS only).
- Link to the page from the event's public navigation, if a plugin hook
  allows it; otherwise share the URL directly.

Out:
- Favourites, search, filters, timezone switching, embed widget.
- Any change to the existing schedule or schedule editor.

## Data

Use the current published schedule only:

```python
schedule = request.event.current_schedule  # None -> 404 or "no schedule yet"
talks = schedule.scheduled_talks  # visible, has room/start/submission
breaks = schedule.breaks  # slot_type=BREAK, has room, no submission
```

Source: `src/pretalx/schedule/models/schedule.py` (`scheduled_talks`,
`breaks`). Track: `slot.submission.track`. Speakers:
`slot.submission.sorted_speakers` (check the name on the installed version).

Breaks are stored per room, so the same break shows up once for each room.
Remove duplicates by `(start, end, description)` before rendering.

## Permissions

Same rule as the built-in schedule: `ScheduleView` uses
`permission_required = "schedule.view_schedule"`
(`src/pretalx/agenda/views/schedule.py`). Use pretalx's `PermissionRequired`
mixin with that permission so the page is hidden exactly when the schedule
is (unreleased, `show_schedule` feature flag off, etc.).

## Layout

CSS grid per day:
- Rows: time slices (e.g. 5 or 15 min) from the day's first start to its
  last end; a session spans `grid-row: <start slice> / <end slice>`.
- Columns: a time-label column, then for each track `lanes(track)` columns.
  The track header spans its lanes.
- Lane assignment, per track per day: sort sessions by start; put each in the
  first lane whose last session ended at or before this start, else open a new
  lane. `lanes(track)` = number of lanes used. O(n log n) per track.
- Breaks: `grid-column: 2 / -1`.

Do the lane and slice maths in the view (or a small pure function), not the
template, so it can be unit-tested.

## Plugin skeleton

Copy the structure of `plugins/pretalx-resubmit`:

```
plugins/pretalx-track-schedule/
  pyproject.toml          # name, version, pretalx>=2026.2.1,<2026.3, entry point
  README.md
  run-tests.sh            # same as pretalx-resubmit's
  pretalx_track_schedule/
    __init__.py
    apps.py               # PluginApp + PretalxPluginMeta, category "FEATURE"
    urls.py               # path("<slug:event>/p/track-schedule/", ...)
    views.py
    layout.py             # lane + slice maths (pure)
    templates/pretalx_track_schedule/schedule.html
    static/pretalx_track_schedule/schedule.css
  tests/
    conftest.py, requirements.txt, track_schedule_test_settings.py
    test_layout.py        # lanes, overlaps, back-to-back, break dedupe
    test_view.py          # 200 when released, hidden when not, no-track column
```

Enable it per event in Settings → Plugins after deploying.

## Acceptance

- Two sessions in the same track at the same time in different rooms sit
  side by side, without overlapping.
- Back-to-back sessions (end == next start) share a lane.
- A break that exists in N rooms is rendered once, across all columns.
- Sessions without a track appear in "No track".
- The page returns 404 or denies access whenever `/<event>/schedule/` does.
- Plugin tests pass via `./run-tests.sh` against the built image.

## Effort

About 1 day including tests.

## Before starting

Check every pretalx name used above (`scheduled_talks`, `breaks`,
`sorted_speakers`, `PermissionRequired`, `schedule.view_schedule`) against the
installed `PRETALX_VERSION`, not this repo's `src/`, which may differ from the
release.

## References

- pretalx plugin docs: https://docs.pretalx.org/developer/plugins/
- Built-in schedule view: `src/pretalx/agenda/views/schedule.py`
- Existing plugin to copy: `plugins/pretalx-resubmit/`
