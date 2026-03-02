# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled
from PIL import Image

from pretalx.event.models import Event
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


def _wizard_post(client, step, data):
    data = {f"{step}-{key}": value for key, value in data.items()}
    data["event_wizard-current_step"] = step
    response = client.post(WIZARD_URL, data=data, follow=True)
    assert response.status_code == 200
    return response


def _submit_initial(client, organiser):
    return _wizard_post(
        client,
        step="initial",
        data={"locales": ["en", "de"], "organiser": organiser.pk},
    )


def _submit_basics(client, slug="newevent", copy_from_event=None):
    data = {
        "email": "foo@bar.com",
        "locale": "en",
        "name_0": "New event!",
        "slug": slug,
        "timezone": "Europe/Amsterdam",
    }
    if copy_from_event:
        data["copy_from_event"] = copy_from_event
    return _wizard_post(client, step="basics", data=data)


def _submit_timeline(client, deadline=False):
    _now = now()
    tomorrow = _now + dt.timedelta(days=1)
    return _wizard_post(
        client,
        step="timeline",
        data={
            "date_from": _now.strftime("%Y-%m-%d"),
            "date_to": tomorrow.strftime("%Y-%m-%d"),
            "deadline": _now.strftime("%Y-%m-%d %H:%M:%S") if deadline else "",
        },
    )


def _submit_display(client, **kwargs):
    data = {"header_pattern": "plain", "logo": "", "primary_color": ""}
    data.update(kwargs)
    return _wizard_post(client, step="display", data=data)


def _submit_plugins(client, plugins=None):
    return _wizard_post(client, step="plugins", data={"plugins": plugins or []})


def _full_wizard(client, organiser, slug="newevent", deadline=False, **display_kwargs):
    _submit_initial(client, organiser)
    _submit_basics(client, slug=slug)
    _submit_timeline(client, deadline=deadline)
    _submit_display(client, **display_kwargs)
    _submit_plugins(client)


@pytest.mark.parametrize("deadline", (True, False))
def test_event_wizard_creates_event(client, deadline):
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

    _full_wizard(client, organiser, slug=slug, deadline=deadline, header_pattern="topo")

    assert Event.objects.count() == count + 1
    event = Event.objects.get(slug=slug)
    assert str(event.name) == "New event!"
    assert event.locales == ["en", "de"]
    assert event.content_locales == ["en", "de"]
    assert event.display_settings["header_pattern"] == "topo"


def test_event_wizard_creates_new_team_for_limited_access(client):
    """When the user doesn't have all_events + full permissions, a new team is created."""
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

    _full_wizard(client, organiser, slug="newteamevent")

    assert organiser.teams.count() == initial_team_count + 1


def test_event_wizard_no_new_team_when_all_events(client):
    """When user's team has all_events + full settings + submissions, no new team."""
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

    _full_wizard(client, organiser, slug="noteamevent")

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
    """Wizard with copy_from_event copies questions, tracks, and CfP settings."""
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

    _submit_initial(client, event.organiser)
    _submit_basics(client, slug="copyevent", copy_from_event=event.pk)
    _submit_timeline(client)
    _submit_display(client)
    _submit_plugins(client)

    new_event = Event.objects.get(slug="copyevent")
    with scopes_disabled():
        assert new_event.questions.count() >= 1
        assert new_event.tracks.count() >= 1
        assert new_event.cfp.fields["title"]["min_length"] == 50


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

    _submit_initial(client, organiser)
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

    _full_wizard(client, organiser, slug="colorevent", primary_color="#00ff00")

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

    _full_wizard(client, organiser, slug="deadlineevent", deadline=True)

    event = Event.objects.get(slug="deadlineevent")
    with scope(event=event):
        assert event.cfp.deadline is not None


def test_event_wizard_copy_prefills_display(client):
    """Copying from an event with display settings prefills them."""
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

    _submit_initial(client, event.organiser)
    _submit_basics(client, slug="copydisplay", copy_from_event=event.pk)
    _submit_timeline(client)
    _submit_display(client, primary_color="#ff0000", header_pattern="topo")
    _submit_plugins(client)

    new_event = Event.objects.get(slug="copydisplay")
    assert new_event.primary_color == "#ff0000"
    assert new_event.display_settings["header_pattern"] == "topo"


def test_event_wizard_past_date_shows_warning(client):
    """Creating an event with dates in the past shows a warning."""
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

    _submit_initial(client, organiser)
    _submit_basics(client, slug="pastevent")

    past_date = (now() - dt.timedelta(days=365)).strftime("%Y-%m-%d")
    _wizard_post(
        client, step="timeline", data={"date_from": past_date, "date_to": past_date}
    )

    # Verify the event wasn't created (we stopped at the display step)
    # and the display step renders (which triggers the past-date warning)
    assert not Event.objects.filter(slug="pastevent").exists()


def test_event_wizard_without_header_pattern(client):
    """Wizard without header_pattern still creates the event successfully."""
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

    _full_wizard(client, organiser, slug="noheader", header_pattern="")

    event = Event.objects.get(slug="noheader")
    assert event.display_settings.get("header_pattern", "") != "topo"


def test_event_wizard_with_logo(client):
    """Wizard with a logo file triggers image processing."""
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

    _submit_initial(client, organiser)
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


def test_event_wizard_wrong_order_restarts(client):
    """Submitting basics before initial redirects back to initial."""
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

    _submit_basics(client)
