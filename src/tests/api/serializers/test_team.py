import pytest
from django_scopes import scopes_disabled
from rest_framework import exceptions

from pretalx.api.serializers.team import (
    TeamInviteSerializer,
    TeamMemberSerializer,
    TeamSerializer,
)
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_team_member_serializer_fields():
    user = UserFactory(name="Ada Lovelace", email="ada@example.com")

    serializer = TeamMemberSerializer(user)
    data = serializer.data

    assert data["code"] == user.code
    assert data["name"] == "Ada Lovelace"
    assert data["email"] == "ada@example.com"


@pytest.mark.django_db
def test_team_invite_serializer_fields():
    invite = TeamInviteFactory(email="invited@example.com")

    serializer = TeamInviteSerializer(invite)
    data = serializer.data

    assert data["id"] == invite.pk
    assert data["email"] == "invited@example.com"
    assert data["token"] == invite.token


@pytest.mark.django_db
def test_team_serializer_init_scopes_querysets_to_organiser():
    """Querysets include the organiser's own data and exclude other organisers' data."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    track = TrackFactory(event=event)
    invite = TeamInviteFactory(team__organiser=organiser)

    other_organiser = OrganiserFactory()
    EventFactory(organiser=other_organiser)
    TrackFactory(event=EventFactory(organiser=other_organiser))
    TeamInviteFactory(team__organiser=other_organiser)

    with scopes_disabled():
        serializer = TeamSerializer(
            context={"request": make_api_request(organiser=organiser)}
        )

    assert list(serializer.fields["limit_events"].queryset) == [event]
    with scopes_disabled():
        assert list(serializer.fields["limit_tracks"].queryset) == [track]
    assert list(serializer.fields["invites"].queryset) == [invite]


@pytest.mark.django_db
def test_team_serializer_init_with_instance_scopes_members():
    """When initialized with an existing team, members queryset is scoped to that team."""
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    member = UserFactory()
    team.members.add(member)
    UserFactory()

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    assert list(serializer.fields["members"].queryset) == [member]


@pytest.mark.django_db
def test_team_serializer_validate_requires_events():
    """Validation fails when neither all_events nor limit_events is set."""
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=False)

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    with pytest.raises(exceptions.ValidationError):
        serializer.validate({"all_events": False, "limit_events": []})


@pytest.mark.django_db
def test_team_serializer_validate_requires_permissions():
    organiser = OrganiserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_submissions=False
    )

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    with pytest.raises(exceptions.ValidationError):
        serializer.validate(
            {
                "all_events": True,
                "can_create_events": False,
                "can_change_teams": False,
                "can_change_organiser_settings": False,
                "can_change_event_settings": False,
                "can_change_submissions": False,
                "is_reviewer": False,
            }
        )


@pytest.mark.django_db
def test_team_serializer_validate_accepts_all_events_with_permission():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    result = serializer.validate({"all_events": True, "can_change_submissions": True})
    assert result["all_events"] is True


@pytest.mark.django_db
def test_team_serializer_validate_accepts_limit_events_with_permission():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=False)

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    result = serializer.validate(
        {"all_events": False, "limit_events": [event], "is_reviewer": True}
    )
    assert result["limit_events"] == [event]


@pytest.mark.django_db
def test_team_serializer_validate_falls_back_to_instance():
    """Validation uses instance values when keys are missing from data (partial update)."""
    organiser = OrganiserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_submissions=True
    )

    with scopes_disabled():
        serializer = TeamSerializer(
            instance=team, context={"request": make_api_request(organiser=organiser)}
        )

    result = serializer.validate({})
    assert result == {}


@pytest.mark.django_db
def test_team_serializer_create_sets_organiser_from_request():
    organiser = OrganiserFactory()

    with scopes_disabled():
        serializer = TeamSerializer(
            context={"request": make_api_request(organiser=organiser)}
        )
        team = serializer.create(
            {"name": "New Team", "all_events": True, "can_change_submissions": True}
        )

    assert team.organiser == organiser
    assert team.name == "New Team"


@pytest.mark.django_db
def test_team_serializer_init_without_organiser_uses_empty_querysets():
    with scopes_disabled():
        serializer = TeamSerializer(context={"request": make_api_request()})

    assert list(serializer.fields["limit_events"].child_relation.queryset) == []
    with scopes_disabled():
        assert list(serializer.fields["limit_tracks"].child_relation.queryset) == []
    assert list(serializer.fields["invites"].child_relation.queryset) == []


@pytest.mark.django_db
def test_team_serializer_serializes_all_fields():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)

    with scopes_disabled():
        serializer = TeamSerializer(
            team, context={"request": make_api_request(organiser=organiser)}
        )
        data = serializer.data

    expected_fields = {
        "id",
        "name",
        "members",
        "invites",
        "all_events",
        "limit_events",
        "limit_tracks",
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
        "is_reviewer",
        "force_hide_speaker_names",
    }
    assert set(data.keys()) == expected_fields
