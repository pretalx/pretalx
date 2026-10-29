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


def test_generate_invite_token_returns_unique_lowercase_alphanumerics():
    tokens = {generate_invite_token() for _ in range(10)}

    assert len(tokens) == 10
    allowed = set(string.ascii_lowercase + string.digits)
    for token in tokens:
        assert set(token).issubset(allowed)


@pytest.mark.parametrize(
    "duplicate_slug", ("unique-org", "Unique-Org"), ids=("exact", "case_insensitive")
)
def test_organiser_slug_uniqueness(duplicate_slug):
    OrganiserFactory(slug="unique-org")
    with pytest.raises(IntegrityError):
        Organiser.objects.create(name="Duplicate", slug=duplicate_slug)


def test_organiser_clean_lowercases_slug():
    organiser = Organiser(name="Test", slug="MixedCase")

    organiser.full_clean()

    assert organiser.slug == "mixedcase"
    assert organiser.organiser is organiser


def test_organiser_clean_defers_empty_slug_to_field_validation():
    organiser = Organiser(name="Test", slug="")

    with pytest.raises(ValidationError) as excinfo:
        organiser.full_clean()

    assert excinfo.value.message_dict == {"slug": ["This field cannot be blank."]}


def test_organiser_clean_reports_case_insensitive_duplicate_on_slug():
    OrganiserFactory(slug="Legacy")
    organiser = Organiser(name="Other", slug="legacy")

    with pytest.raises(ValidationError) as excinfo:
        organiser.full_clean()

    assert list(excinfo.value.message_dict) == ["slug"]


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


@pytest.mark.parametrize(
    ("url_attr", "expected"),
    (
        ("base", "/orga/organiser/myorg/"),
        ("settings", "/orga/organiser/myorg/settings/"),
        ("delete", "/orga/organiser/myorg/settings/delete/"),
        ("teams", "/orga/organiser/myorg/teams/"),
        ("new_team", "/orga/organiser/myorg/teams/new/"),
    ),
)
def test_organiser_orga_urls(url_attr, expected):
    organiser = OrganiserFactory(slug="myorg")
    assert getattr(organiser.orga_urls, url_attr) == expected


def test_team_permission_set_lists_active_permissions_with_display_names():
    team = TeamFactory(
        can_create_events=True,
        can_change_teams=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
    )
    empty = TeamFactory(
        can_create_events=False,
        can_change_teams=False,
        can_change_submissions=False,
        can_change_event_settings=False,
        can_change_organiser_settings=False,
        is_reviewer=False,
        force_hide_speaker_names=False,
    )

    assert team.permission_set == {
        "can_create_events",
        "can_change_teams",
        "is_reviewer",
    }
    assert team.permission_set_display == {
        Team._meta.get_field(attr).verbose_name
        for attr in ("can_create_events", "can_change_teams", "is_reviewer")
    }
    assert empty.permission_set == set()
    assert empty.permission_set_display == set()


def test_team_events_follow_all_events_flag():
    organiser = OrganiserFactory()
    event1 = EventFactory(organiser=organiser)
    event2 = EventFactory(organiser=organiser)
    EventFactory()
    all_events_team = TeamFactory(organiser=organiser, all_events=True)
    limited_team = TeamFactory(organiser=organiser, all_events=False)
    limited_team.limit_events.add(event1)

    assert set(all_events_team.events) == {event1, event2}
    assert list(limited_team.events) == [event1]


@pytest.mark.parametrize(
    ("url_attr", "suffix"), (("base", "/"), ("delete", "/delete/"))
)
def test_team_orga_urls(url_attr, suffix):
    organiser = OrganiserFactory(slug="myorg")
    team = TeamFactory(organiser=organiser)
    expected = f"/orga/organiser/myorg/teams/{team.pk}{suffix}"
    assert getattr(team.orga_urls, url_attr) == expected


def test_team_invite_generates_token_and_derives_organiser_and_url():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser)

    invite = TeamInviteFactory(team=team)

    assert invite.organiser == organiser
    assert len(invite.token) == 32
    assert invite.invitation_url == settings.SITE_URL + reverse(
        "orga:invitation.view", kwargs={"code": invite.token}
    )


def test_team_invite_token_unique():
    invite1 = TeamInviteFactory()
    with pytest.raises(IntegrityError):
        TeamInviteFactory(
            team=invite1.team, email="other@example.com", token=invite1.token
        )
