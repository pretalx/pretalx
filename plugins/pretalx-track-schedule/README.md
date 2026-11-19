# pretalx-track-schedule

A public schedule page with one column per **track** instead of per room, at
`/<event>/p/track-schedule/`. The built-in schedule stays as it is.

## Setup

1. Enable the "Schedule by track" plugin in the event's settings (Plugins).
2. Turn on tracks for the event and give sessions a track. Sessions without a
   track are shown in a "No track" column.

The page shows the current published schedule. It is visible exactly when
the built-in schedule is: it checks the same permission
(`schedule.view_schedule`) on the same schedule, so it is a 404 before the
first release, for non-public events, or with the schedule turned off.

The schedule pages (Schedule, Sessions, Speakers, and this one) get a "By
track" tab after pretalx's own tabs, whenever the schedule is visible. pretalx
has no plugin hook for these tabs, so a small script
(`static/pretalx_track_schedule/tab.js`) adds it to the server-rendered tab
bar; without JavaScript the tab is missing, and the footer link ("Schedule by
track", on every event page) still leads there.

## Colours by answer (e.g. difficulty)

Settings → Schedule by track: pick a choice question asked per proposal, such
as "Difficulty", and a colour per answer. Common names start with a colour
(Easy green, Medium amber, Hard red, Mixed purple). Session cards then take
the colour of their answer, with the answer as a label, and the page shows a
legend; sessions without an answer keep their track colour. With several
answers (multiple choice), the first answer in the question's order wins.
Track colours stay on the column headers.

## Layout

- One section per day, in the event timezone, with links to each day.
- Tracks in their configured order (`position`), then "No track".
- Sessions of a track that overlap in time sit side by side in lanes;
  back-to-back sessions share a lane.
- Breaks are stored once per room; each is shown once, across all tracks.
- Cards: time, room, title (linking to the session page) and speakers, with
  the track colour.
- Below 48rem width, the grid becomes a list per track (CSS only).

The lane and time-slice maths is in `pretalx_track_schedule/layout.py`, with
no Django dependencies.

## Tests

```sh
./run-tests.sh            # uses the pretalx-sso:latest image; set IMAGE= to change
IMAGE=pretalx:local ./run-tests.sh -k layout
```
