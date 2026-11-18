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
        enable_plugin(event, "pretalx_fixed_sessions")
    return event


@pytest.fixture
def organiser():
    from pretalx.event.models import Organiser

    return Organiser.objects.create(name="Org", slug="org")


@pytest.fixture
def event(organiser):
    return _make_event(organiser, "camp", days=60)


@pytest.fixture
def orga(event):
    from pretalx.event.models import Team
    from pretalx.person.models import User

    user = User.objects.create_user(
        email="orga@example.invalid", password="orga-pw", name="Orga"
    )
    team = Team.objects.create(
        organiser=event.organiser,
        name="Orga",
        all_events=True,
        can_change_submissions=True,
        can_change_event_settings=True,
    )
    team.members.add(user)
    return user


@pytest.fixture
def core_type(event):
    from pretalx_fixed_sessions.models import FixedSession
    from pretalx.submission.models import SubmissionType

    submission_type = SubmissionType.objects.create(
        event=event, name="Intro to Contact Staff", default_duration=60
    )
    FixedSession.objects.create(
        submission_type=submission_type,
        title="Intro to Contact Staff",
        abstract="Fixed abstract",
        description="Fixed description",
    )
    return submission_type


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
            **{"submission_type": event.cfp.default_type, **fields},
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
