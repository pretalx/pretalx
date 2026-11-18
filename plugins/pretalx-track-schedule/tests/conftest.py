import datetime as dt

import pytest
from django.core.cache import cache
from django.test import Client
from django_scopes import scopes_disabled


@pytest.fixture(autouse=True)
def _isolation(db):
    cache.clear()
    with scopes_disabled():
        yield


def _make_event(organiser, slug, *, plugin=True, days=0):
    from pretalx.event.domain.event import create_event
    from pretalx.event.domain.plugins import enable_plugin

    day = dt.date.today() + dt.timedelta(days=days)
    # create_event also sets up the CfP and its default session type
    event = create_event(
        organiser=organiser,
        locales=["en"],
        name=slug.title(),
        slug=slug,
        date_from=day,
        date_to=day,
        email="orga@example.invalid",
    )
    event.is_public = True
    event.save()
    if plugin:
        enable_plugin(event, "pretalx_track_schedule")
    return event


@pytest.fixture
def organiser():
    from pretalx.event.models import Organiser

    return Organiser.objects.create(name="Org", slug="org")


@pytest.fixture
def event(organiser):
    event = _make_event(organiser, "camp", days=30)
    event.feature_flags["use_tracks"] = True
    event.save()
    return event


@pytest.fixture
def rooms(event):
    from pretalx.schedule.models import Room

    return [Room.objects.create(event=event, name=f"Room {n}") for n in (1, 2, 3)]


@pytest.fixture
def at(event):
    """at(hour, minute) on the event's first day, in the event timezone."""

    def make(hour, minute=0):
        return dt.datetime.combine(
            event.date_from, dt.time(hour, minute), tzinfo=event.tz
        )

    return make


@pytest.fixture
def schedule_slot(event, make_proposal):
    """Puts a confirmed proposal into the work-in-progress schedule."""
    from pretalx.schedule.models import TalkSlot

    def make(title, room, start, end, track=None, speakers=()):
        proposal = make_proposal(
            event, title, *speakers, state="confirmed", track=track
        )
        slot = proposal.slots.filter(schedule=event.wip_schedule).first() or TalkSlot(
            submission=proposal, schedule=event.wip_schedule
        )
        slot.room, slot.start, slot.end = room, start, end
        slot.save()
        return proposal

    return make


@pytest.fixture
def add_break(event):
    from pretalx.schedule.models import TalkSlot

    def make(room, start, end, description="Lunch"):
        return TalkSlot.objects.create(
            schedule=event.wip_schedule,
            room=room,
            start=start,
            end=end,
            slot_type="break",
            description=description,
        )

    return make


@pytest.fixture
def release(event):
    from pretalx.schedule.domain.release import freeze_schedule

    def make(name="v1"):
        freeze_schedule(event.wip_schedule, name, notify_speakers=False)
        event.refresh_from_db()

    return make


@pytest.fixture
def speaker():
    from pretalx.person.models import User

    return User.objects.create_user(
        email="speaker@example.invalid", password="speaker-pw", name="Speaker"
    )


@pytest.fixture
def make_proposal():
    from pretalx.submission.models import Submission

    def make(event, title, *speakers, state="rejected", **fields):
        submission = Submission.objects.create(
            event=event,
            title=title,
            state=state,
            submission_type=event.cfp.default_type,
            **fields,
        )
        for position, user in enumerate(speakers):
            submission.speakers.add(
                user.get_speaker(event), through_defaults={"position": position}
            )
        return submission

    return make


@pytest.fixture
def client_for():
    def make(user=None):
        # pretalx answers unknown hosts with 404; this is the test site's host
        client = Client(HTTP_HOST="pretalx.example.invalid")
        if user:
            client.force_login(user)
        return client

    return make
