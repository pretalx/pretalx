# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import QueryDict

from pretalx.orga.views.organiser import (
    OrganiserDetail,
    OrganiserSpeakerList,
    TeamMemberDelete,
    TeamView,
)
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_team_view_get_queryset_returns_organiser_teams(event):
    team = TeamFactory(organiser=event.organiser, name="Alpha Team")
    team.members.add(UserFactory())
    TeamFactory(name="Other Org Team")
    user = make_orga_user(event, can_change_teams=True, teams=[team])
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert list(qs) == [team]
    assert qs.first().member_count == 2


def test_team_view_invite_form_only_on_update(event):
    team = TeamFactory(organiser=event.organiser)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.method = "GET"
    listing = make_view(TeamView, request)
    listing.action = "list"
    listing.object = None
    update = make_view(TeamView, request)
    update.action = "update"
    update.object = team

    assert listing.invite_form is None
    assert update.invite_form is not None


def test_team_member_mixin_get_object_returns_member(event):
    team = TeamFactory(organiser=event.organiser)
    member = UserFactory()
    team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(TeamMemberDelete, request, team_pk=team.pk, user_pk=member.pk)

    assert view.get_object() == member


def test_organiser_detail_get_object_returns_request_organiser(event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    with_organiser = make_view(
        OrganiserDetail, make_request(event, user=user, organiser=event.organiser)
    )
    without_organiser = make_view(OrganiserDetail, make_request(event, user=user))

    assert with_organiser.get_object() == event.organiser
    assert without_organiser.get_object() is None


@pytest.mark.parametrize("is_admin", (True, False))
def test_organiser_detail_context_delete_link_requires_admin(is_admin):
    event = EventFactory()
    user = UserFactory(is_administrator=is_admin)
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_organiser_settings=True
    )
    team.members.add(user)
    request = make_request(event, user=user, organiser=event.organiser)
    view = make_view(OrganiserDetail, request)
    view.object = event.organiser

    context = view.get_context_data()

    assert ("submit_buttons_extra" in context) is is_admin
    assert "submit_buttons" in context


def test_organiser_speaker_list_get_queryset_annotates_counts(event):
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state="submitted")
    submitted.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, organiser=event.organiser)
    request.GET = QueryDict()
    view = make_view(OrganiserSpeakerList, request)

    result = list(view.get_queryset())

    assert list(view.events) == [event]
    assert result == [speaker.user]
    assert result[0].submission_count == 2
    assert result[0].accepted_submission_count == 1
