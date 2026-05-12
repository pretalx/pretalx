# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django.http import QueryDict

from pretalx.orga.views.organiser import (
    OrganiserDelete,
    OrganiserDetail,
    OrganiserSpeakerList,
    TeamMemberDelete,
    TeamResend,
    TeamResetPassword,
    TeamUninvite,
    TeamView,
    speaker_search,
)
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TeamInviteFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_team_view_get_queryset_returns_organiser_teams(event):
    """get_queryset returns teams belonging to the request organiser."""
    team = TeamFactory(organiser=event.organiser, name="Alpha Team")
    team.members.add(UserFactory())
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert team in qs
    assert hasattr(qs.first(), "member_count")


def test_team_view_get_queryset_excludes_other_organiser_teams(event):
    other_team = TeamFactory(name="Other Org Team")
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert other_team not in qs


def test_team_view_get_form_kwargs_includes_organiser(event):
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "create"
    view.object = None

    kwargs = view.get_form_kwargs()

    assert kwargs["organiser"] == event.organiser


def test_team_view_get_generic_permission_object_returns_organiser(event):
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)

    assert view.get_generic_permission_object() == event.organiser


@pytest.mark.parametrize(
    ("action", "expected_fragment"), (("create", "New team"), ("list", "Teams"))
)
def test_team_view_get_generic_title_without_instance(event, action, expected_fragment):
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = action

    title = view.get_generic_title()

    assert expected_fragment in str(title)


def test_team_view_get_generic_title_with_instance(event):
    team = TeamFactory(organiser=event.organiser, name="My Team")
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "update"

    title = view.get_generic_title(instance=team)

    assert "My Team" in str(title)


def test_team_view_invite_form_none_on_list(event):
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "list"
    view.object = None

    assert view.invite_form is None


def test_team_view_invite_form_returned_on_update(event):
    team = TeamFactory(organiser=event.organiser)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.method = "GET"
    view = make_view(TeamView, request)
    view.action = "update"
    view.object = team

    form = view.invite_form

    assert form is not None


@pytest.mark.parametrize("view_class", (TeamUninvite, TeamResend))
def test_invite_mixin_action_object_name_returns_email(event, view_class):
    team = TeamFactory(organiser=event.organiser)
    invite = TeamInviteFactory(team=team, email="test@example.com")
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(view_class, request, pk=team.pk, invite_pk=invite.pk)

    assert view.action_object_name() == "test@example.com"


@pytest.mark.parametrize("view_class", (TeamUninvite, TeamResend))
def test_invite_mixin_action_back_url_points_to_team(event, view_class):
    team = TeamFactory(organiser=event.organiser)
    invite = TeamInviteFactory(team=team)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(view_class, request, pk=team.pk, invite_pk=invite.pk)

    assert view.action_back_url == team.orga_urls.base


def test_team_member_delete_action_object_name_includes_name_and_email(event):
    team = TeamFactory(organiser=event.organiser)
    member = UserFactory(name="Alice", email="alice@example.com")
    team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamMemberDelete, request, team_pk=team.pk, user_pk=member.pk)

    name = view.action_object_name()

    assert "Alice" in name
    assert "alice@example.com" in name


def test_team_member_delete_action_back_url_points_to_team(event):
    team = TeamFactory(organiser=event.organiser)
    member = UserFactory()
    team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamMemberDelete, request, team_pk=team.pk, user_pk=member.pk)

    assert view.action_back_url == team.orga_urls.base


def test_team_member_mixin_get_object_returns_member(event):
    team = TeamFactory(organiser=event.organiser)
    member = UserFactory()
    team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamMemberDelete, request, team_pk=team.pk, user_pk=member.pk)

    assert view.get_object() == member


def test_team_reset_password_action_title(event):
    team = TeamFactory(organiser=event.organiser)
    member = UserFactory()
    team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamResetPassword, request, team_pk=team.pk, user_pk=member.pk)

    assert str(view.action_title) == "Reset password"


def test_organiser_detail_get_object_returns_request_organiser(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDetail, request)

    assert view.get_object() == event.organiser


def test_organiser_detail_get_object_returns_none_without_organiser(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    request = make_request(event, user=user)
    view = make_view(OrganiserDetail, request)

    assert view.get_object() is None


def test_organiser_detail_get_permission_object_returns_object(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDetail, request)

    assert view.get_permission_object() == event.organiser


def test_organiser_detail_get_success_url_returns_current_path(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    request = make_request(event, user=user, organiser=event.organiser, path="/test/")
    view = make_view(OrganiserDetail, request)

    assert view.get_success_url() == "/test/"


def test_organiser_detail_context_includes_delete_link_for_admin():
    event = EventFactory()
    user = UserFactory(is_administrator=True)
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_organiser_settings=True
    )
    team.members.add(user)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDetail, request)
    view.object = event.organiser

    context = view.get_context_data()

    assert "submit_buttons_extra" in context
    assert "submit_buttons" in context


def test_organiser_detail_context_no_delete_link_for_non_admin(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDetail, request)
    view.object = event.organiser

    context = view.get_context_data()

    assert "submit_buttons_extra" not in context
    assert "submit_buttons" in context


def test_organiser_delete_get_object_returns_request_organiser(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDelete, request)

    assert view.get_object() == event.organiser


def test_organiser_delete_get_permission_object_returns_user(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDelete, request)

    assert view.get_permission_object() == user


def test_organiser_delete_action_object_name_includes_organiser_name(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDelete, request)

    name = view.action_object_name()

    assert str(event.organiser.name) in name


def test_organiser_delete_action_back_url_points_to_settings(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDelete, request)

    assert view.action_back_url == event.organiser.orga_urls.settings


def test_organiser_speaker_list_get_permission_object_returns_organiser(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserSpeakerList, request)

    assert view.get_permission_object() == event.organiser


def test_organiser_speaker_list_events_uses_user_access(event):
    """The events property returns events the user has speaker access to."""
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserSpeakerList, request)

    events = view.events

    assert event in events


def test_organiser_speaker_list_get_queryset_returns_speakers(event):
    """get_queryset returns users with speaker profiles for accessible events."""
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event, state="accepted")
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("role=all")
    view = make_view(OrganiserSpeakerList, request)

    result = list(view.get_queryset())

    assert speaker.user in result


def test_organiser_speaker_list_get_queryset_annotates_counts(event):
    """get_queryset annotates submission_count and accepted_submission_count."""
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state="submitted")
    submitted.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("role=all")
    view = make_view(OrganiserSpeakerList, request)

    result = list(view.get_queryset())

    assert result[0].submission_count == 2
    assert result[0].accepted_submission_count == 1


def test_organiser_speaker_list_get_table_data_returns_object_list(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserSpeakerList, request)
    view.object_list = ["sentinel"]

    assert view.get_table_data() == ["sentinel"]


def test_speaker_search_returns_empty_for_short_query(event):
    """Searches shorter than 3 characters return empty results."""
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=ab")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 0
    assert data["results"] == []


def test_speaker_search_returns_empty_without_query(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict()

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 0
    assert data["results"] == []


def test_speaker_search_finds_speakers_by_name(event):
    """Searches matching speaker name return results."""
    speaker = SpeakerFactory(event=event, user__name="Uniquename Testperson")
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=Uniquename")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 1
    assert data["results"][0]["name"] == "Uniquename Testperson"


def test_speaker_search_finds_speakers_by_email(event):
    speaker = SpeakerFactory(event=event, user__email="uniqueemail@example.com")
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=uniqueemail")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 1
    assert data["results"][0]["email"] == "uniqueemail@example.com"


def test_speaker_search_does_not_return_speakers_from_inaccessible_events(event):
    """speaker_search only returns speakers from events the user has access to."""
    other_event = EventFactory()
    speaker = SpeakerFactory(event=other_event, user__name="Inaccessible Speaker")
    sub = SubmissionFactory(event=other_event)
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=Inaccessible")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 0


def test_speaker_search_excludes_users_without_submissions(event):
    SpeakerFactory(event=event, user__name="Profileonly Person")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=Profileonly")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 0


def test_speaker_search_excludes_users_with_only_draft_submissions(event):
    speaker = SpeakerFactory(event=event, user__name="Draftonly Person")
    sub = SubmissionFactory(event=event, state="draft")
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("search=Draftonly")

    response = speaker_search(request)

    data = json.loads(response.content)
    assert data["count"] == 0


def test_organiser_speaker_list_get_table_data_falls_back_to_queryset(event):
    """When object_list is not set, get_table_data falls back to get_queryset."""
    speaker = SpeakerFactory(event=event)
    sub = SubmissionFactory(event=event)
    sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict("role=all")
    view = make_view(OrganiserSpeakerList, request)

    data = list(view.get_table_data())

    assert speaker.user in data
