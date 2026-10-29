# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.event.models import Event
from pretalx.orga.views.event import EventWizard
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    QuestionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]

WIZARD_URL = "/orga/event/new/"


@pytest.fixture(autouse=True)
def _reset_timezone_state():
    """The wizard creates events with ``Europe/Amsterdam`` and makes client
    requests against them, so EventMiddleware activates that timezone on
    the thread-local and never deactivates. Reset afterwards so subsequent
    tests reading ``timezone.get_current_timezone_name()`` see the default."""
    yield
    timezone.deactivate()


def _make_creator(organiser, **team_kwargs):
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
            **team_kwargs,
        )
        team.members.add(user)
    return user


def _wizard_post(client, step, data, goto_step=None):
    data = {f"{step}-{key}": value for key, value in data.items()}
    data["event_wizard-current_step"] = step
    if goto_step:
        data["wizard_goto_step"] = goto_step
    response = client.post(WIZARD_URL, data=data, follow=True)
    assert response.status_code == 200
    return response


def _submit_organiser(client, organiser, copy_from_event=None):
    data = {"organiser": organiser.pk}
    if copy_from_event:
        data["copy_from_event"] = copy_from_event
    return _wizard_post(client, step="organiser", data=data)


def _submit_localisation(
    client,
    locales=("en", "de"),
    locale="en",
    timezone_name="Europe/Amsterdam",
    goto_step=None,
):
    return _wizard_post(
        client,
        step="localisation",
        data={"locales": list(locales), "locale": locale, "timezone": timezone_name},
        goto_step=goto_step,
    )


def _submit_basics(
    client,
    slug="newevent",
    date_from=None,
    date_to=None,
    deadline=None,
    goto_step=None,
    **extra,
):
    _now = now()
    tomorrow = _now + dt.timedelta(days=1)
    return _wizard_post(
        client,
        step="basics",
        data={
            "email": "foo@bar.com",
            "name_0": "New event!",
            "slug": slug,
            "date_from": date_from or _now.strftime("%Y-%m-%d"),
            "date_to": date_to or tomorrow.strftime("%Y-%m-%d"),
            "deadline": deadline or "",
            **extra,
        },
        goto_step=goto_step,
    )


def _submit_display(client, **kwargs):
    data = {"header_pattern": "plain", "logo": "", "primary_color": ""}
    data.update(kwargs)
    return _wizard_post(client, step="display", data=data)


def _submit_plugins(client, plugins=None):
    return _wizard_post(client, step="plugins", data={"plugins": plugins or []})


def _full_wizard(
    client,
    organiser=None,
    slug="newevent",
    deadline=None,
    locales=("en", "de"),
    locale="en",
    plugins=None,
    **display_kwargs,
):
    if organiser:
        _submit_organiser(client, organiser)
    _submit_localisation(client, locales=locales, locale=locale)
    _submit_basics(client, slug=slug, deadline=deadline)
    _submit_display(client, **display_kwargs)
    _submit_plugins(client, plugins=plugins)


def test_event_wizard_creates_event(client, make_image):
    organiser = OrganiserFactory()
    user = _make_creator(organiser)
    client.force_login(user)
    count = Event.objects.count()
    slug = f"newevent{now().year}"

    _full_wizard(
        client,
        slug=slug,
        deadline="2035-06-01 12:00:00",
        header_pattern="topo",
        primary_color="#00ff00",
        logo=make_image(),
        plugins=["tests.dummy_app"],
    )

    assert Event.objects.count() == count + 1
    assert organiser.teams.count() == 1
    event = Event.objects.get(slug=slug)
    assert str(event.name) == "New event!"
    assert event.locales == ["en", "de"]
    assert event.content_locales == ["en", "de"]
    assert event.locale == "en"
    assert event.display_settings["header_pattern"] == "topo"
    assert event.primary_color == "#00ff00"
    assert event.logo
    assert event.plugin_list == ["tests.dummy_app"]

    _full_wizard(
        client,
        organiser,
        slug="germanevent",
        locales=("de",),
        locale="de",
        header_pattern="",
    )

    event = Event.objects.get(slug="germanevent")
    assert event.locales == ["de"]
    assert event.content_locales == ["de"]
    assert event.locale == "de"
    assert event.display_settings["header_pattern"] == ""
    assert event.primary_color == ""
    assert not event.logo
    assert event.plugin_list == []


def test_event_wizard_creates_new_team_for_limited_access(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Limited",
            can_create_events=True,
            can_change_event_settings=False,
            can_change_submissions=False,
            all_events=False,
        )
        team.members.add(user)
    client.force_login(user)

    _full_wizard(client, slug="newteamevent")

    with scopes_disabled():
        new_team = organiser.teams.exclude(pk=team.pk).get()
        assert list(new_team.limit_events.all()) == [
            Event.objects.get(slug="newteamevent")
        ]
        assert list(new_team.members.all()) == [user]


def test_event_wizard_rejects_duplicate_slug_and_warns_about_past_dates(client, event):
    user = _make_creator(event.organiser)
    client.force_login(user)
    count = Event.objects.count()
    past_date = (now() - dt.timedelta(days=365)).strftime("%Y-%m-%d")

    _submit_organiser(client, event.organiser)
    _submit_localisation(client)
    response = _submit_basics(client, slug=event.slug)

    assert response.context["wizard"]["steps"].current == "basics"
    assert list(response.context["form"].errors) == ["slug"]

    response = _submit_basics(
        client, slug="pastevent", date_from=past_date, date_to=past_date
    )

    assert response.context["wizard"]["steps"].current == "display"
    assert [str(message) for message in response.context["messages"]] == [
        f"Please consider including your event’s year in the slug, e.g. myevent{now().year % 100}.",
        "Did you really mean to make your event take place in the past?",
    ]
    assert Event.objects.count() == count


def test_event_wizard_with_copy(client):
    from tests.dummy_app.signals import copied_events  # noqa: PLC0415

    with scopes_disabled():
        source = EventFactory(
            cfp__fields={"title": {"min_length": 50}},
            timezone="Pacific/Auckland",
            locales=["de"],
            locale="de",
            primary_color="#ff0000",
            display_settings={"header_pattern": "topo"},
        )
        QuestionFactory(event=source)
        track = TrackFactory(event=source, name="Security")
        reviewers = TeamFactory(
            organiser=source.organiser, all_events=False, is_reviewer=True
        )
        reviewers.limit_events.add(source)
        reviewers.limit_tracks.add(track)
    user = _make_creator(source.organiser, can_change_teams=True)
    client.force_login(user)

    response = _submit_organiser(client, source.organiser, copy_from_event=source.pk)

    fields = response.context["form"].fields
    assert fields["timezone"].initial == "Pacific/Auckland"
    assert fields["locale"].initial == "de"
    assert fields["locales"].initial == ["de"]
    assert "data-autofill" not in fields["timezone"].widget.attrs

    _submit_localisation(client)
    response = _submit_basics(client, slug="copyevent", add_to_teams="on")

    assert response.context["form"]["primary_color"].value() == "#ff0000"
    assert response.context["form"]["header_pattern"].value() == "topo"

    _submit_display(client, primary_color="#ff0000", header_pattern="topo")
    _submit_plugins(client, plugins=["tests.dummy_app"])

    new_event = Event.objects.get(slug="copyevent")
    assert ("copyevent", source.slug) in copied_events
    assert new_event.primary_color == "#ff0000"
    assert new_event.display_settings["header_pattern"] == "topo"
    assert new_event.locales == ["en", "de"]
    assert new_event.content_locales == ["en", "de"]
    with scopes_disabled():
        assert new_event.questions.count() == 1
        new_track = new_event.tracks.get()
        assert new_event.cfp.fields["title"]["min_length"] == 50
        assert set(reviewers.limit_events.all()) == {source, new_event}
        assert set(reviewers.limit_tracks.all()) == {track, new_track}

    _submit_organiser(client, source.organiser, copy_from_event=source.pk)
    _submit_localisation(client)
    _submit_basics(client, slug="copyeventnoteams")
    _submit_display(client)
    _submit_plugins(client)

    with scopes_disabled():
        assert set(reviewers.limit_events.all()) == {source, new_event}
        assert set(reviewers.limit_tracks.all()) == {track, new_track}
        assert Event.objects.get(slug="copyeventnoteams").tracks.count() == 1


def test_event_wizard_changing_copy_source_reseeds_copied_steps(client, make_image):
    with scopes_disabled():
        first = EventFactory(
            timezone="Pacific/Auckland",
            locales=["de"],
            locale="de",
            primary_color="#111111",
        )
        second = EventFactory(
            organiser=first.organiser,
            timezone="America/New_York",
            locales=["en"],
            locale="en",
            primary_color="#222222",
        )
    user = _make_creator(first.organiser)
    client.force_login(user)

    _submit_organiser(client, first.organiser, copy_from_event=first.pk)
    _submit_localisation(client, timezone_name="Europe/Amsterdam")
    response = _submit_organiser(client, first.organiser, copy_from_event=first.pk)

    assert response.context["form"]["timezone"].value() == "Europe/Amsterdam"

    _submit_localisation(client)
    _submit_basics(client)
    _submit_display(client, primary_color="#111111", logo=make_image())
    (logo_file,) = client.session["wizard_event_wizard"]["step_files"][
        "display"
    ].values()
    response = _submit_organiser(client, first.organiser, copy_from_event=second.pk)

    assert not EventWizard.file_storage.exists(logo_file["tmp_name"])
    form = response.context["form"]
    assert form["timezone"].value() == "America/New_York"
    assert form["locale"].value() == "en"
    assert form["locales"].value() == ["en"]
    response = _submit_localisation(client, goto_step="display")
    assert response.context["form"]["primary_color"].value() == "#222222"


def test_event_wizard_keeps_organiser_step_after_losing_access(client):
    with scopes_disabled():
        event = EventFactory()
        user = _make_creator(event.organiser)
        team = user.teams.get()
        fallback = OrganiserFactory()
        fallback_team = TeamFactory(
            organiser=fallback, name="Fallback", can_create_events=True, all_events=True
        )
        fallback_team.members.add(user)
    client.force_login(user)
    count = Event.objects.count()

    _submit_organiser(client, event.organiser)
    _submit_localisation(client)
    with scopes_disabled():
        team.delete()
    _submit_basics(client, slug="lostaccess")
    _submit_display(client)
    _submit_plugins(client)

    assert Event.objects.count() == count


def test_event_wizard_with_deadline_sets_cfp_deadline(client):
    organiser = OrganiserFactory()
    user = _make_creator(organiser)
    client.force_login(user)

    _submit_organiser(client, organiser)
    response = _submit_localisation(client)
    same_request_hint = response.context["form"].fields["deadline"].widget.timezone_name
    response = _submit_basics(
        client, slug="deadlineevent", deadline="2035-06-01 12:00:00", goto_step="basics"
    )
    stored_hint = response.context["form"].fields["deadline"].widget.timezone_name
    _submit_display(client)
    _submit_plugins(client)

    assert same_request_hint == "Europe/Amsterdam"
    assert stored_hint == "Europe/Amsterdam"
    event = Event.objects.get(slug="deadlineevent")
    with scope(event=event):
        assert event.cfp.deadline == dt.datetime(
            2035, 6, 1, 12, tzinfo=ZoneInfo("Europe/Amsterdam")
        )


def test_event_wizard_restarts_when_step_data_is_lost(client):
    organiser = OrganiserFactory()
    user = _make_creator(organiser)
    client.force_login(user)

    response = _submit_basics(client, slug="nostorageevent")

    assert response.context["wizard"]["steps"].current == "localisation"
    assert set(response.context["wizard"]["form"].errors) == {
        "locales",
        "locale",
        "timezone",
    }

    _submit_localisation(client)
    client.get(WIZARD_URL)
    response = _submit_basics(client, slug="lostevent")

    assert response.context["wizard"]["steps"].current == "localisation"
    assert not response.context["wizard"]["form"].is_bound
    assert not Event.objects.filter(slug__in=["nostorageevent", "lostevent"]).exists()
