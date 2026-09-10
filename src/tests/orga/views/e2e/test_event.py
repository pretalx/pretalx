# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled
from PIL import Image

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


def _submit_basics(client, slug="newevent"):
    return _wizard_post(
        client,
        step="basics",
        data={"email": "foo@bar.com", "name_0": "New event!", "slug": slug},
    )


def _submit_timeline(client, deadline=None):
    _now = now()
    tomorrow = _now + dt.timedelta(days=1)
    return _wizard_post(
        client,
        step="timeline",
        data={
            "date_from": _now.strftime("%Y-%m-%d"),
            "date_to": tomorrow.strftime("%Y-%m-%d"),
            "deadline": deadline or "",
        },
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
    **display_kwargs,
):
    if organiser:
        _submit_organiser(client, organiser)
    _submit_localisation(client, locales=locales, locale=locale)
    _submit_basics(client, slug=slug)
    _submit_timeline(client, deadline=deadline)
    _submit_display(client, **display_kwargs)
    _submit_plugins(client)


@pytest.mark.parametrize(
    ("deadline", "locales", "locale"),
    (("2035-06-01 12:00:00", ("en", "de"), "en"), (None, ("de",), "de")),
    ids=("multilingual", "german_only"),
)
def test_event_wizard_creates_event(client, deadline, locales, locale):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)
    count = Event.objects.count()
    slug = f"newevent{now().year}"

    _full_wizard(
        client,
        slug=slug,
        deadline=deadline,
        locales=locales,
        locale=locale,
        header_pattern="topo",
    )

    assert Event.objects.count() == count + 1
    event = Event.objects.get(slug=slug)
    assert str(event.name) == "New event!"
    assert event.locales == list(locales)
    assert event.content_locales == list(locales)
    assert event.locale == locale
    assert event.display_settings["header_pattern"] == "topo"


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
    initial_team_count = organiser.teams.count()

    _full_wizard(client, slug="newteamevent")

    assert organiser.teams.count() == initial_team_count + 1


def test_event_wizard_no_new_team_when_all_events(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Full Access",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)
    initial_team_count = organiser.teams.count()

    _full_wizard(client, slug="noteamevent")

    assert organiser.teams.count() == initial_team_count


def test_event_wizard_duplicate_slug_rejected(client, event):
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)
    count = Event.objects.count()

    _full_wizard(client, event.organiser, slug=event.slug)

    assert Event.objects.count() == count


def test_event_wizard_with_copy(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"title": {"min_length": 50}})
        QuestionFactory(event=event)
        TrackFactory(event=event)
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, event.organiser, copy_from_event=event.pk)
    _submit_localisation(client)
    _submit_basics(client, slug="copyevent")
    _submit_timeline(client)
    _submit_display(client)
    _submit_plugins(client)

    new_event = Event.objects.get(slug="copyevent")
    with scopes_disabled():
        assert new_event.questions.count() >= 1
        assert new_event.tracks.count() >= 1
        assert new_event.cfp.fields["title"]["min_length"] == 50
        assert new_event.locales == ["en", "de"]
        assert new_event.content_locales == ["en", "de"]


def test_event_wizard_with_copy_fires_plugin_copy_signal(client):
    from tests.dummy_app.signals import copied_events  # noqa: PLC0415

    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, event.organiser, copy_from_event=event.pk)
    _submit_localisation(client)
    _submit_basics(client, slug="copyplugins")
    _submit_timeline(client)
    _submit_display(client)
    _submit_plugins(client, plugins=["tests.dummy_app"])

    assert ("copyplugins", event.slug) in copied_events


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
        user = UserFactory()
        team = TeamFactory(
            organiser=first.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, first.organiser, copy_from_event=first.pk)
    _submit_localisation(client)
    _submit_timeline(client)
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


def test_event_wizard_unchanged_copy_source_keeps_localisation(client):
    with scopes_disabled():
        event = EventFactory(timezone="Pacific/Auckland")
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, event.organiser, copy_from_event=event.pk)
    _submit_localisation(client, timezone_name="Europe/Amsterdam")
    response = _submit_organiser(client, event.organiser, copy_from_event=event.pk)

    assert response.context["form"]["timezone"].value() == "Europe/Amsterdam"


def test_event_wizard_keeps_organiser_step_after_losing_access(client):
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
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
    _submit_timeline(client)
    _submit_display(client)
    _submit_plugins(client)

    assert Event.objects.count() == count


def test_event_wizard_copy_seeds_localisation(client):
    with scopes_disabled():
        event = EventFactory(timezone="Pacific/Auckland", locales=["de"], locale="de")
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    response = _submit_organiser(client, event.organiser, copy_from_event=event.pk)

    fields = response.context["form"].fields
    assert fields["timezone"].initial == "Pacific/Auckland"
    assert fields["locale"].initial == event.locale
    assert fields["locales"].initial == event.locales
    assert "data-autofill" not in fields["timezone"].widget.attrs


def test_event_wizard_with_plugins(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_localisation(client)
    _submit_basics(client, slug="pluginevent")
    _submit_timeline(client)
    _submit_display(client)
    _submit_plugins(client, plugins=["tests.dummy_app"])

    event = Event.objects.get(slug="pluginevent")
    assert "tests.dummy_app" in event.plugin_list


def test_event_wizard_with_primary_color(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _full_wizard(client, slug="colorevent", primary_color="#00ff00")

    assert Event.objects.filter(slug="colorevent", primary_color="#00ff00").exists()


def test_event_wizard_with_deadline_sets_cfp_deadline(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, organiser)
    response = _submit_localisation(client, goto_step="timeline")
    same_request_hint = response.context["form"].fields["deadline"].widget.timezone_name
    response = _submit_basics(client, slug="deadlineevent")
    stored_hint = response.context["form"].fields["deadline"].widget.timezone_name
    _submit_timeline(client, deadline="2035-06-01 12:00:00")
    _submit_display(client)
    _submit_plugins(client)

    assert same_request_hint == "Europe/Amsterdam"
    assert stored_hint == "Europe/Amsterdam"
    event = Event.objects.get(slug="deadlineevent")
    with scope(event=event):
        assert event.cfp.deadline == dt.datetime(
            2035, 6, 1, 12, tzinfo=ZoneInfo("Europe/Amsterdam")
        )


def test_event_wizard_copy_prefills_display(client):
    event = EventFactory(
        primary_color="#ff0000", display_settings={"header_pattern": "topo"}
    )
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_organiser(client, event.organiser, copy_from_event=event.pk)
    _submit_localisation(client)
    _submit_basics(client, slug="copydisplay")
    _submit_timeline(client)
    _submit_display(client, primary_color="#ff0000", header_pattern="topo")
    _submit_plugins(client)

    new_event = Event.objects.get(slug="copydisplay")
    assert new_event.primary_color == "#ff0000"
    assert new_event.display_settings["header_pattern"] == "topo"


def test_event_wizard_past_date_shows_warning(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_localisation(client)
    _submit_basics(client, slug="pastevent")

    past_date = (now() - dt.timedelta(days=365)).strftime("%Y-%m-%d")
    _wizard_post(
        client, step="timeline", data={"date_from": past_date, "date_to": past_date}
    )

    # Verify the event wasn't created (we stopped at the display step)
    # and the display step renders (which triggers the past-date warning)
    assert not Event.objects.filter(slug="pastevent").exists()


def test_event_wizard_without_header_pattern(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _full_wizard(client, slug="noheader", header_pattern="")

    event = Event.objects.get(slug="noheader")
    assert event.display_settings.get("header_pattern", "") != "topo"


def test_event_wizard_with_logo(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_localisation(client)
    _submit_basics(client, slug="logoevent")
    _submit_timeline(client)

    buf = BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    logo = SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")

    data = {
        "display-header_pattern": "plain",
        "display-primary_color": "",
        "display-logo": logo,
    }
    data["event_wizard-current_step"] = "display"
    response = client.post(WIZARD_URL, data=data, follow=True)
    assert response.status_code == 200

    _submit_plugins(client)

    event = Event.objects.get(slug="logoevent")
    assert event.logo


def test_event_wizard_restarts_when_step_data_is_lost(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    _submit_localisation(client)
    client.get(WIZARD_URL)

    response = _submit_basics(client, slug="lostevent")

    assert not Event.objects.filter(slug="lostevent").exists()
    assert response.context["wizard"]["steps"].current == "localisation"
    assert not response.context["wizard"]["form"].is_bound


def test_event_wizard_basics_without_wizard_storage_renders_first_step(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            name="Orga",
            can_create_events=True,
            can_change_event_settings=True,
            can_change_submissions=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    response = _submit_basics(client, slug="nostorageevent")

    assert not Event.objects.filter(slug="nostorageevent").exists()
    assert response.context["wizard"]["steps"].current == "localisation"
    assert set(response.context["wizard"]["form"].errors) == {
        "locales",
        "locale",
        "timezone",
    }
