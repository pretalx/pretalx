# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import string

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.urls import reverse

from pretalx.event.models import Organiser, Team
from pretalx.event.models.organiser import generate_invite_token
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_generate_invite_token_character_set():
    token = generate_invite_token()
    allowed = set(string.ascii_lowercase + string.digits)
    assert set(token).issubset(allowed)


def test_generate_invite_token_returns_unique_values():
    tokens = {generate_invite_token() for _ in range(10)}
    assert len(tokens) == 10


def test_organiser_str_returns_name():
    organiser = OrganiserFactory(name="My Org")
    assert str(organiser) == "My Org"


def test_organiser_slug_uniqueness():
    OrganiserFactory(slug="unique-org")
    with pytest.raises(IntegrityError):
        Organiser.objects.create(name="Duplicate", slug="unique-org")


@pytest.mark.parametrize(
    "slug", ("my-org", "org123", "a1b2"), ids=("dashes", "numbers", "mixed")
)
def test_organiser_slug_accepts_valid_formats(slug):
    organiser = Organiser(name="Test", slug=slug)
    organiser.clean_fields()


@pytest.mark.parametrize(
    "slug",
    ("-start", "end-", "no spaces", "special!char"),
    ids=("dash_start", "dash_end", "spaces", "special"),
)
def test_organiser_slug_rejects_invalid_formats(slug):
    organiser = Organiser(name="Test", slug=slug)
    with pytest.raises(ValidationError):
        organiser.clean_fields()


def test_organiser_organiser_property_returns_self():
    organiser = OrganiserFactory()
    assert organiser.organiser is organiser


@pytest.mark.parametrize(
    ("url_attr", "expected"),
    (
        ("base", "/orga/organiser/myorg/"),
        ("settings", "/orga/organiser/myorg/settings/"),
        ("delete", "/orga/organiser/myorg/settings/delete/"),
        ("teams", "/orga/organiser/myorg/teams/"),
        ("new_team", "/orga/organiser/myorg/teams/new/"),
        ("user_search", "/orga/organiser/myorg/api/users/"),
    ),
)
def test_organiser_orga_urls(url_attr, expected):
    organiser = OrganiserFactory(slug="myorg")
    assert getattr(organiser.orga_urls, url_attr) == expected


def test_team_str():
    organiser = OrganiserFactory(name="Org")
    team = TeamFactory(organiser=organiser, name="Admins")
    assert str(team) == "Admins on Org"


def test_team_permission_set_includes_active_permissions():
    team = TeamFactory(
        can_create_events=True,
        can_change_teams=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
    )
    assert team.permission_set == {
        "can_create_events",
        "can_change_teams",
        "is_reviewer",
    }


def test_team_permission_set_empty_when_no_permissions():
    team = TeamFactory(
        can_create_events=False,
        can_change_teams=False,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
        is_reviewer=False,
        force_hide_speaker_names=False,
    )
    assert team.permission_set == set()


def test_team_permission_set_display_returns_verbose_names():
    team = TeamFactory(
        can_create_events=True,
        can_change_teams=False,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
        is_reviewer=False,
    )
    display = team.permission_set_display

    assert len(display) == 1
    verbose = Team._meta.get_field("can_create_events").verbose_name
    assert verbose in display


def test_team_events_returns_all_organiser_events_when_all_events():
    organiser = OrganiserFactory()
    event1 = EventFactory(organiser=organiser)
    event2 = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)

    assert set(team.events) == {event1, event2}


def test_team_events_returns_limited_events_when_not_all_events():
    organiser = OrganiserFactory()
    event1 = EventFactory(organiser=organiser)
    EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=False)
    team.limit_events.add(event1)

    assert list(team.events) == [event1]


@pytest.mark.parametrize(
    ("url_attr", "suffix"), (("base", "/"), ("delete", "/delete/"))
)
def test_team_orga_urls(url_attr, suffix):
    organiser = OrganiserFactory(slug="myorg")
    team = TeamFactory(organiser=organiser)
    expected = f"/orga/organiser/myorg/teams/{team.pk}{suffix}"
    assert getattr(team.orga_urls, url_attr) == expected


def test_team_invite_str():
    invite = TeamInviteFactory(email="test@example.com")
    result = str(invite)
    assert "test@example.com" in result


def test_team_invite_organiser_returns_team_organiser():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser)
    invite = TeamInviteFactory(team=team)

    assert invite.organiser == organiser


def test_team_invite_token_is_auto_generated():
    invite = TeamInviteFactory()
    assert invite.token is not None
    assert len(invite.token) == 32


def test_team_invite_token_unique():
    invite1 = TeamInviteFactory()
    with pytest.raises(IntegrityError):
        TeamInviteFactory(
            team=invite1.team, email="other@example.com", token=invite1.token
        )


def test_team_invite_invitation_url():
    invite = TeamInviteFactory()

    expected = settings.SITE_URL + reverse(
        "orga:invitation.view", kwargs={"code": invite.token}
    )
    assert invite.invitation_url == expected
