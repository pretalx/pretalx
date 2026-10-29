# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.interfaces.forms import OrganiserForm, TeamForm, TeamInviteForm
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_team_form_init_new_team_scopes_events_and_tracks_to_organiser(event):
    EventFactory()  # other organiser's event, should not appear
    track = TrackFactory(event=event)
    TrackFactory()  # track on another organiser's event, should not appear

    form = TeamForm(organiser=event.organiser)

    assert list(form.fields["limit_events"].queryset) == [event]
    assert list(form.fields["limit_tracks"].queryset) == [track]


def test_team_form_init_existing_team_scopes_tracks_to_limit_events(event):
    EventFactory()  # other organiser's event, should not appear
    track = TrackFactory(event=event)
    other_event = EventFactory(organiser=event.organiser)
    TrackFactory(event=other_event)
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)

    form = TeamForm(instance=team, organiser=event.organiser)

    assert set(form.fields["limit_events"].queryset) == {event, other_event}
    assert list(form.fields["limit_tracks"].queryset) == [track]


@pytest.mark.parametrize(
    ("overrides", "errors"),
    (
        ({}, {}),
        ({"all_events": False, "limit_events": "event"}, {}),
        ({"can_change_submissions": False, "can_create_events": True}, {}),
        ({"can_change_submissions": False, "can_change_teams": True}, {}),
        ({"can_change_submissions": False, "can_change_organiser_settings": True}, {}),
        ({"can_change_submissions": False, "can_change_event_settings": True}, {}),
        ({"can_change_submissions": False, "is_reviewer": True}, {}),
        (
            {"all_events": False},
            {
                "limit_events": [
                    "Please either pick some events, or grant access to all your events!"
                ]
            },
        ),
        (
            {"can_change_submissions": False},
            {"__all__": ["Please pick at least one permission for this team!"]},
        ),
    ),
    ids=(
        "all_events",
        "limit_events",
        "only_can_create_events",
        "only_can_change_teams",
        "only_can_change_organiser_settings",
        "only_can_change_event_settings",
        "only_is_reviewer",
        "no_events",
        "no_permissions",
    ),
)
def test_team_form_clean(event, overrides, errors):
    data = {
        "name": "Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
        **overrides,
    }
    if data["limit_events"] == "event":
        data["limit_events"] = [event.pk]

    form = TeamForm(data=data, organiser=event.organiser)

    assert form.is_valid() == (not errors)
    assert form.errors == errors


def test_team_form_save_sets_organiser_and_all_events_clears_limit_events(event):
    organiser = event.organiser
    team = TeamFactory(organiser=organiser, all_events=False)
    team.limit_events.add(event)
    data = {
        "name": "New Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [event.pk],
        "limit_tracks": [],
    }

    created = TeamForm(data=data, organiser=organiser)
    assert created.is_valid(), created.errors
    assert created.save().organiser == organiser

    form = TeamForm(data=data, instance=team, organiser=organiser)
    assert form.is_valid(), form.errors
    team = form.save()

    assert team.organiser == organiser
    assert team.name == "New Team"
    assert team.all_events is True
    assert list(team.limit_events.all()) == []


def test_team_form_read_only_disables_fields_and_rejects_changes(event):
    data = {
        "name": "Sneaky Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=event.organiser, read_only=True)

    assert all(field.disabled for field in form.fields.values())
    assert not form.is_valid()


@pytest.mark.parametrize(
    ("emails", "cleaned", "errors"),
    (
        ("test@example.com", ["test@example.com"], {}),
        ("a@example.com\nb@example.com", ["a@example.com", "b@example.com"], {}),
        ("  a@example.com  ,  b@example.com  ", ["a@example.com", "b@example.com"], {}),
        (
            "valid@example.com\nnot-an-email",
            None,
            {"emails": ["Please enter only valid email addresses: not-an-email"]},
        ),
        ("", None, {"emails": ["This field is required."]}),
    ),
    ids=("single", "multiple", "stripped", "invalid", "empty"),
)
def test_team_invite_form_clean_emails(emails, cleaned, errors):
    form = TeamInviteForm(data={"emails": emails})

    assert form.is_valid() == (not errors)
    assert form.errors == errors
    assert form.cleaned_data.get("emails") == cleaned


def test_team_invite_form_init_read_only_disables_all_fields():
    form = TeamInviteForm(read_only=True)

    assert all(field.disabled for field in form.fields.values())


def test_organiser_form_slug_disabled_on_edit():
    organiser = OrganiserFactory()
    form = OrganiserForm(instance=organiser)

    assert form.fields["slug"].disabled is True


def test_organiser_form_create_saves_with_editable_slug():
    data = {"name_0": "My Org", "slug": "my-org"}
    form = OrganiserForm(data=data)

    assert form.fields["slug"].disabled is False
    assert form.is_valid(), form.errors
    organiser = form.save()

    assert str(organiser.name) == "My Org"
    assert organiser.slug == "my-org"
