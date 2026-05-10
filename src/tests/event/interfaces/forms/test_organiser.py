# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.interfaces.forms import OrganiserForm, TeamForm, TeamInviteForm
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_team_form_init_new_team_uses_organiser_events(event):
    """When creating a new team, limit_events queryset only includes
    events belonging to the provided organiser."""
    EventFactory()  # other organiser's event, should not appear
    organiser = event.organiser
    form = TeamForm(organiser=organiser)

    assert list(form.fields["limit_events"].queryset) == [event]


def test_team_form_init_existing_team_uses_instance_organiser(event):
    """When editing an existing team, limit_events queryset only includes
    events belonging to the team's own organiser."""
    EventFactory()  # other organiser's event, should not appear
    team = TeamFactory(organiser=event.organiser, all_events=True)

    form = TeamForm(instance=team, organiser=event.organiser)

    assert list(form.fields["limit_events"].queryset) == [event]


def test_team_form_init_limit_tracks_with_all_events(event):
    """When the team has all_events or no limit_events, limit_tracks
    queryset covers all tracks for the organiser but excludes others."""
    organiser = event.organiser
    track = TrackFactory(event=event)
    TrackFactory()  # track on another organiser's event, should not appear

    form = TeamForm(organiser=organiser)

    assert list(form.fields["limit_tracks"].queryset) == [track]


def test_team_form_init_limit_tracks_scoped_to_limit_events(event):
    """When an existing team has specific limit_events and all_events is
    False, limit_tracks queryset is narrowed to those events' tracks."""
    organiser = event.organiser
    track = TrackFactory(event=event)
    other_event = EventFactory(organiser=organiser)
    TrackFactory(event=other_event)

    team = TeamFactory(organiser=organiser, all_events=False)
    team.limit_events.add(event)

    form = TeamForm(instance=team, organiser=organiser)

    assert list(form.fields["limit_tracks"].queryset) == [track]


def test_team_form_save_sets_organiser(event):
    organiser = event.organiser
    data = {
        "name": "New Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)
    assert form.is_valid(), form.errors

    team = form.save()

    assert team.organiser == organiser
    assert team.name == "New Team"


def test_team_form_clean_rejects_no_events_and_not_all_events(event):
    organiser = event.organiser
    data = {
        "name": "New Team",
        "all_events": False,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert not form.is_valid()
    assert "limit_events" in form.errors


def test_team_form_clean_rejects_no_permissions(event):
    organiser = event.organiser
    data = {
        "name": "No Permission Team",
        "all_events": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.parametrize(
    "permission",
    (
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
        "is_reviewer",
    ),
)
def test_team_form_clean_accepts_any_single_permission(event, permission):
    organiser = event.organiser
    data = {
        "name": "Single Perm Team",
        "all_events": True,
        permission: True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("all_events", "use_limit_events"),
    ((True, False), (False, True)),
    ids=("all_events", "limit_events"),
)
def test_team_form_clean_accepts_events_via_all_or_limit(
    event, all_events, use_limit_events
):
    organiser = event.organiser
    data = {
        "name": "Team",
        "all_events": all_events,
        "can_change_submissions": True,
        "limit_events": [event.pk] if use_limit_events else [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert form.is_valid(), form.errors


def test_team_form_init_read_only_disables_all_fields(event):
    organiser = event.organiser
    form = TeamForm(organiser=organiser, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_team_form_clean_read_only_rejects_changes(event):
    organiser = event.organiser
    data = {
        "name": "Sneaky Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser, read_only=True)

    assert not form.is_valid()


def test_team_invite_form_clean_multiple_emails():
    data = {"emails": "a@example.com\nb@example.com"}
    form = TeamInviteForm(data=data)
    assert form.is_valid(), form.errors

    assert form.cleaned_data["emails"] == ["a@example.com", "b@example.com"]


def test_team_invite_form_clean_invalid_email_adds_error():
    data = {"emails": "valid@example.com\nnot-an-email"}
    form = TeamInviteForm(data=data)

    assert not form.is_valid()
    assert "emails" in form.errors


def test_team_invite_form_clean_requires_at_least_one_email():
    data = {"emails": ""}
    form = TeamInviteForm(data=data)

    assert not form.is_valid()
    assert "emails" in form.errors


def test_team_invite_form_clean_accepts_single_email():
    data = {"emails": "test@example.com"}
    form = TeamInviteForm(data=data)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["emails"] == ["test@example.com"]


def test_team_invite_form_clean_strips_whitespace():
    data = {"emails": "  a@example.com  ,  b@example.com  "}
    form = TeamInviteForm(data=data)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["emails"] == ["a@example.com", "b@example.com"]


def test_team_invite_form_init_read_only_disables_all_fields():
    form = TeamInviteForm(read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_organiser_form_init_name_is_required():
    form = OrganiserForm()
    assert form.fields["name"].required is True


def test_organiser_form_slug_disabled_on_edit():
    organiser = OrganiserFactory()
    form = OrganiserForm(instance=organiser)

    assert form.fields["slug"].disabled is True


def test_organiser_form_slug_enabled_on_create():
    form = OrganiserForm()

    assert form.fields["slug"].disabled is False


def test_organiser_form_valid_data_saves():
    data = {"name_0": "My Org", "slug": "my-org"}
    form = OrganiserForm(data=data)
    assert form.is_valid(), form.errors

    organiser = form.save()

    assert str(organiser.name) == "My Org"
    assert organiser.slug == "my-org"
