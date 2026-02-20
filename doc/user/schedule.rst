.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-guide-schedule`:

Scheduling
==========

Once you have accepted sessions, the next step is to arrange them into a
schedule: assigning each session a room, a day, and a start time. pretalx
provides an interactive drag-and-drop editor for this, along with a versioning
system that lets you refine the schedule before and after publishing it.

.. _`user-guide-schedule-concepts`:

How Scheduling Works
--------------------

The schedule in pretalx is built around two core ideas: **rooms** where sessions
take place, and **schedule versions** that let you prepare and refine the
schedule before making it public.

.. _`user-guide-schedule-rooms`:

Rooms
^^^^^

Rooms represent the physical or virtual spaces where sessions happen. Each room
has a name, an optional description (shown to attendees, useful for directions),
and optional speaker information (shown only to scheduled speakers, useful for
technical details like available hardware or room capacity).

You manage rooms under **Your event → Schedule → Rooms**. You can reorder rooms
by dragging them – the order on this page determines the column order in the
schedule editor and the public schedule.

You need to create at least one room before you can start scheduling.

.. _`user-guide-schedule-availabilities`:

Availabilities
^^^^^^^^^^^^^^

Both rooms and speakers can have **availabilities** – time windows when they are
available. Availabilities serve as constraints for scheduling: pretalx will warn
you when a session is scheduled outside the available times of its room or any of
its speakers.

**Room availabilities** are set by organisers on the room's settings page. If you
don't set any availabilities for a room, pretalx treats it as available for the
entire event. If you set availabilities, the room is only considered available
during those time windows. Use this when a room is only available on certain days
or at certain hours.

**Speaker availabilities** are collected from speakers as part of the
submission process if you enable the availability field in the CfP editor (see
:ref:`user-guide-cfp`). Speakers fill in their availability using a visual
calendar widget during submission, and can update it later from their profile.
When a session has multiple speakers, pretalx uses the intersection of their
availabilities to determine when the session can be scheduled.

If you set room availabilities, speakers can only pick times for their
availabilities that are inside the combined room availabilities.

The schedule editor visualises availabilities directly on the grid: available
times are shown clearly, while unavailable times are greyed out, making it easy
to spot conflicts at a glance. If you schedule a session at a time where a
speaker or the room is unavailable, you will also see a small warning icon in
the session box.

.. _`user-guide-schedule-versions`:

Schedule Versions
^^^^^^^^^^^^^^^^^

pretalx uses a versioning system for schedules. At any time, your event has
exactly one **work-in-progress (WIP) schedule** – this is your internal draft
that only organisers can see.

When you are happy with the current state of your schedule, you **release** it
as a named version (e.g. "v1", "Day 1 preview", or any name you choose). This
creates a snapshot that becomes the public schedule, visible to speakers and
attendees. After a release, a new WIP schedule is created automatically for you
to continue editing.

This means you can move sessions around, try different arrangements, and fix
problems without the public seeing any of your work-in-progress changes. The
public schedule only changes when you explicitly release a new version.

You can release as many versions as you need. Each release is recorded with a
timestamp, and attendees can see a changelog of what changed between versions.
Releasing a version also lets you notify speakers of their scheduled times and
review any conflicts — see :ref:`user-guide-schedule-release` for the full
release workflow.

.. tip::

   Don't wait for a perfect schedule before releasing – release early and
   iterate. Attendees appreciate seeing a schedule take shape, and the built-in
   changelog makes it easy for them to spot what changed between versions.

.. _`user-guide-schedule-items`:

What Goes on the Schedule
-------------------------

The schedule can contain two kinds of items:

**Sessions** are your accepted talks, workshops, and other proposals. They come
from the submission process and carry all their metadata (speakers, track,
abstract, etc.). Only **confirmed** sessions are visible to the public — see
`What becomes public`_ below and the :ref:`session lifecycle
<user-guide-proposals>` for more on session states.

**Schedule-only items** are entries that don't need the full proposal workflow.
There are two types:

- **Breaks** are publicly visible items like lunch breaks, coffee breaks, or
  social events. They appear on the public schedule alongside sessions.
  They do not have speakers or session detail pages.
- **Blockers** are internal planning items that are **never shown publicly**. Use
  them to reserve time slots – for example, to block off a room for setup, to
  mark a time slot as unavailable, or to reserve space for a session you haven't
  confirmed yet.

You create breaks and blockers directly in the schedule editor by dragging them
from the sidebar onto the grid.

If you have many rooms and want a break or a blocker to span all rooms, you can
click on the break in question to open its edit window. There, you can select
"Copy to other rooms". This is useful for lunch or coffee breaks that span all
rooms at the same time.

On the mobile or single-column schedule display, if there multiple breaks at
the same time across multiple rooms, only one of them will be shown.

.. _`user-guide-schedule-editor`:

The Schedule Editor
-------------------

The schedule editor is the main tool for building your schedule. You can find it
at **Your event → Schedule**. It shows a time grid with your rooms as columns
and time slots as rows.

The editor has two main areas: the **sidebar** on the left with unscheduled
sessions, and central **grid** showing the current WIP schedule.

If you have a lot of rooms, consider using the **condensed mode** by clicking
the button at the top of the schedule editor page. In expanded mode, the
schedule looks just like on the public schedule pages, and the unscheduled
sessions sidebar is shown at full width on the left. In condensed mode, the
grid is compressed and the sidebar collapses into a small floating panel in the
bottom right corner, giving you more space for the grid.

Scheduling sessions
^^^^^^^^^^^^^^^^^^^

To schedule a session, drag it from the sidebar onto the grid. Drop it in the
desired room column at the desired start time. The session will snap to the
grid's time intervals.

A short note on the **grid intervals**: You can choose the time resolution of
the grid: 5, 15, 30, or 60 minutes. A finer grid gives you more precision when
placing sessions, while a coarser grid is easier to work with when all your
sessions are standard lengths. Your choice is remembered between visits.
You can also click an interval on the timeline on the left to expand only
that interval to a five minute resolution.

To **move** a scheduled session, drag it to a new position on the grid. To
**unschedule** a session (remove it from the schedule without deleting it),
drag it back to the sidebar, or click the session and use the "Unschedule"
button in the session editor.

The session editor
^^^^^^^^^^^^^^^^^^

Click any item on the grid to open the session editor. For sessions, it shows
speakers, availabilities, track, room, and duration, with a link to the full
session page. For breaks and blockers, you can edit the title and duration.

The editor also shows any **warnings** for the session, such as scheduling
conflicts with speaker availability or room availability.

Warnings
^^^^^^^^

The schedule editor checks for conflicts and shows warnings when:

- A session is scheduled outside its **room's availability** windows if the room has availabilities set
- A session is scheduled when one of its **speakers is unavailable**
- Two sessions in the **same room overlap** in time
- A **speaker is double-booked** (scheduled for two sessions at the same time)

Warnings appear as visual indicators on the grid and in the session editor.

.. _`user-guide-schedule-release`:

Releasing a Schedule
--------------------

When your schedule is ready to be made public, click the **New release** button
in the schedule editor. This takes you to the release page, where you can:

- **Choose a version name** for the release (e.g. "v1", "Final", "Day 1 update").
  Version names must be unique within your event.
- **Review warnings** about the schedule, including unconfirmed sessions (which
  will not be visible to the public), unscheduled sessions, and individual
  session conflicts.
- **Write a public changelog comment** that will appear in the schedule's
  version history and RSS feed.
- **Choose whether to notify speakers** about their scheduled time slots.
  Speaker notifications are generated as emails and placed in the
  :ref:`outbox <user-guide-emails-outbox>` for your review before sending.

After releasing, a new WIP schedule is created automatically, and you can
continue editing. The released version becomes the public schedule.

What becomes public
^^^^^^^^^^^^^^^^^^^

When you release a schedule, only the following items become visible to the
public:

- **Confirmed sessions** that have a scheduled time and room
- **Breaks** that have a scheduled time and room

Items that remain hidden:

- Sessions in any state other than "confirmed" (including accepted-but-unconfirmed)
- Blockers
- Sessions without a scheduled time or room

Confirming a session does not immediately make it appear on the public
schedule — it will only be included in the *next* release. This gives you full
control over when changes to the programme become visible to attendees. In the
schedule editor, you will see not-yet-confirmed sessions as slightly greyed-out
(accepted sessions) or striped (pending accepted).

Speaker notifications
^^^^^^^^^^^^^^^^^^^^^

When you release a schedule, pretalx can generate notification emails for
speakers whose sessions are new or have been moved since the last release.
These emails include an iCal attachment with the session details.

Notification emails are placed in the outbox, so you can review and edit them
before sending. The email template used is "New schedule version" — you can
customise it like any other template (see :ref:`user-guide-emails-templates`).

Making the schedule public
^^^^^^^^^^^^^^^^^^^^^^^^^^

Releasing a schedule version is separate from making the schedule visible. To
control public visibility, use the **Actions → Make schedule public / Hide
schedule** toggle in the schedule editor. You can release schedule versions
while the schedule is hidden – this lets you prepare everything before making
it available to attendees.

.. _`user-guide-schedule-widget`:

Embedding the Schedule
----------------------

You can embed your published schedule on your event website or blog using a
JavaScript widget. The embedded schedule shows the same content as the public
schedule page, and opens session detail pages and speaker profile pages as a
as an overlay over the schedule when clicked.

To get the embed code, go to the **Schedule → Widget**. You can configure the
widget language, the layout, and the selected there, then click "Generate
widget code".

You will get two code snippets. The first loads the widget script and should go
in the ``<head>`` of your page (or in the ``<body>`` if that's more
convenient) and looks similar to this::

    <script type="text/javascript" src="https://pretalx.com/democon/schedule/widget/v2.en.js"></script>

The second creates the widget and should go where you want the schedule to
appear::

    <pretalx-schedule event-url="https://pretalx.com/democon/" locale="en" style="--pretalx-clr-primary: #3aa57c"></pretalx-schedule>
    <noscript>
       <div class="pretalx-widget">
            <div class="pretalx-widget-info-message">
                JavaScript is disabled in your browser. To access our schedule without JavaScript,
                please <a target="_blank" href="https://pretalx.com/democon/schedule/">click here</a>.
            </div>
        </div>
    </noscript>

You can embed multiple widgets for different events on the same page – just
include the script snippet once and then add one widget element per event.
