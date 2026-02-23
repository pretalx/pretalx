import string

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.event.models import Event, Organiser, Team, TeamInvite
from pretalx.event.models.organiser import (
    check_access_permissions,
    generate_invite_token,
)
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_generate_invite_token_character_set():
    token = generate_invite_token()
    allowed = set(string.ascii_lowercase + string.digits)
    assert set(token).issubset(allowed)


def test_generate_invite_token_returns_unique_values():
    tokens = {generate_invite_token() for _ in range(10)}
    assert len(tokens) == 10


@pytest.mark.django_db
def test_check_access_permissions_raises_when_no_team_can_change_teams():
    """Must have at least one team with can_change_teams and members."""
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, can_change_teams=False, can_create_events=True
    )
    team.members.add(user)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


@pytest.mark.parametrize(
    ("missing_perm", "expected_code"),
    (
        ("can_create_events", "no_can_create_events"),
        ("can_change_organiser_settings", "no_can_change_organiser_settings"),
    ),
)
@pytest.mark.django_db
def test_check_access_permissions_warns_when_organiser_level_permission_missing(
    missing_perm, expected_code
):
    organiser = OrganiserFactory()
    user = UserFactory()
    kwargs = {
        "organiser": organiser,
        "can_change_teams": True,
        "can_create_events": True,
        "can_change_organiser_settings": True,
    }
    kwargs[missing_perm] = False
    team = TeamFactory(**kwargs)
    team.members.add(user)

    warnings = check_access_permissions(organiser)

    codes = [code for code, _msg in warnings]
    assert codes == [expected_code]


@pytest.mark.django_db
def test_check_access_permissions_raises_when_event_has_no_team_access():
    """Every event must be covered by at least one team with members."""
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        all_events=False,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


@pytest.mark.django_db
def test_check_access_permissions_warns_when_event_team_lacks_change_settings():
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=False,
        all_events=True,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    warnings = check_access_permissions(organiser)

    codes = [code for code, _msg in warnings]
    assert codes == ["no_can_change_event_settings"]


@pytest.mark.django_db
def test_check_access_permissions_no_warnings_when_all_permissions_present():
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    warnings = check_access_permissions(organiser)

    assert warnings == []


@pytest.mark.django_db
def test_check_access_permissions_ignores_teams_without_members():
    """Teams without members don't count for permission checks."""
    organiser = OrganiserFactory()
    TeamFactory(organiser=organiser, can_change_teams=True)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


@pytest.mark.django_db
def test_check_access_permissions_event_covered_by_limit_events():
    """An event is covered if a team has it in limit_events (not just all_events)."""
    organiser = OrganiserFactory()
    user = UserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        all_events=False,
    )
    team.members.add(user)
    team.limit_events.add(event)

    warnings = check_access_permissions(organiser)

    assert warnings == []


@pytest.mark.django_db
def test_organiser_str_returns_name():
    organiser = OrganiserFactory(name="My Org")
    assert str(organiser) == "My Org"


@pytest.mark.django_db
def test_organiser_slug_uniqueness():
    OrganiserFactory(slug="unique-org")
    with pytest.raises(IntegrityError):
        Organiser.objects.create(name="Duplicate", slug="unique-org")


@pytest.mark.parametrize(
    "slug", ("my-org", "org123", "a1b2"), ids=("dashes", "numbers", "mixed")
)
@pytest.mark.django_db
def test_organiser_slug_accepts_valid_formats(slug):
    organiser = Organiser(name="Test", slug=slug)
    organiser.clean_fields()


@pytest.mark.parametrize(
    "slug",
    ("-start", "end-", "no spaces", "special!char"),
    ids=("dash_start", "dash_end", "spaces", "special"),
)
@pytest.mark.django_db
def test_organiser_slug_rejects_invalid_formats(slug):
    organiser = Organiser(name="Test", slug=slug)
    with pytest.raises(ValidationError):
        organiser.clean_fields()


@pytest.mark.django_db
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
@pytest.mark.django_db
def test_organiser_orga_urls(url_attr, expected):
    organiser = OrganiserFactory(slug="myorg")
    assert getattr(organiser.orga_urls, url_attr) == expected


@pytest.mark.django_db
def test_organiser_shred_deletes_organiser():
    organiser = OrganiserFactory()
    pk = organiser.pk
    organiser.shred()
    assert not Organiser.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_organiser_shred_deletes_related_events():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    event_pk = event.pk

    with scopes_disabled():
        organiser.shred()

    assert not Event.objects.filter(pk=event_pk).exists()


@pytest.mark.django_db
def test_organiser_shred_logs_activity():
    organiser = OrganiserFactory()
    slug = organiser.slug
    user = UserFactory()

    with scopes_disabled():
        organiser.shred(person=user)

    with scopes_disabled():
        log = ActivityLog.objects.filter(action_type="pretalx.organiser.delete").first()
    assert log is not None
    assert log.person == user
    assert log.data["slug"] == slug


@pytest.mark.django_db
def test_team_str():
    organiser = OrganiserFactory(name="Org")
    team = TeamFactory(organiser=organiser, name="Admins")
    assert str(team) == "Admins on Org"


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_team_events_returns_all_organiser_events_when_all_events():
    organiser = OrganiserFactory()
    event1 = EventFactory(organiser=organiser)
    event2 = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)

    with scopes_disabled():
        assert set(team.events) == {event1, event2}


@pytest.mark.django_db
def test_team_events_returns_limited_events_when_not_all_events():
    organiser = OrganiserFactory()
    event1 = EventFactory(organiser=organiser)
    EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=False)
    team.limit_events.add(event1)

    with scopes_disabled():
        assert list(team.events) == [event1]


@pytest.mark.django_db
def test_team_remove_member_removes_from_m2m():
    team = TeamFactory()
    user = UserFactory()
    team.members.add(user)

    team.remove_member(user)

    assert list(team.members.all()) == []


@pytest.mark.django_db
def test_team_remove_member_updates_api_tokens():
    """When a member is removed, their API tokens scoped to this team's
    events should have their events updated."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)
    user = UserFactory()
    team.members.add(user)

    token = UserApiTokenFactory(user=user)
    token.events.add(event)

    team.remove_member(user)

    token.refresh_from_db()
    with scopes_disabled():
        assert list(token.events.all()) == []


@pytest.mark.parametrize(
    ("url_attr", "suffix"), (("base", "/"), ("delete", "/delete/"))
)
@pytest.mark.django_db
def test_team_orga_urls(url_attr, suffix):
    organiser = OrganiserFactory(slug="myorg")
    team = TeamFactory(organiser=organiser)
    expected = f"/orga/organiser/myorg/teams/{team.pk}{suffix}"
    assert getattr(team.orga_urls, url_attr) == expected


@pytest.mark.django_db
def test_team_invite_str():
    invite = TeamInviteFactory(email="test@example.com")
    result = str(invite)
    assert "test@example.com" in result


@pytest.mark.django_db
def test_team_invite_organiser_returns_team_organiser():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser)
    invite = TeamInviteFactory(team=team)

    assert invite.organiser == organiser


@pytest.mark.django_db
def test_team_invite_token_is_auto_generated():
    invite = TeamInviteFactory()
    assert invite.token is not None
    assert len(invite.token) == 32


@pytest.mark.django_db
def test_team_invite_token_unique():
    invite1 = TeamInviteFactory()
    with pytest.raises(IntegrityError):
        TeamInvite.objects.create(
            team=invite1.team, email="other@example.com", token=invite1.token
        )


@pytest.mark.django_db
def test_team_invite_invitation_url():
    invite = TeamInviteFactory()

    expected = settings.SITE_URL + reverse(
        "orga:invitation.view", kwargs={"code": invite.token}
    )
    assert invite.invitation_url == expected


@pytest.mark.django_db
def test_team_invite_send_delivers_email():
    djmail.outbox = []
    invite = TeamInviteFactory(email="speaker@example.com")

    mail = invite.send()

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == ["speaker@example.com"]
    assert invite.invitation_url in sent.body
    assert str(invite.team.organiser.name) in sent.body
    assert mail.to == "speaker@example.com"
    assert "invited" in sent.subject.lower()
