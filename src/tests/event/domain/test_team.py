# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail

from pretalx.event.domain.team import create_team_invites
from tests.factories import TeamFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_team_invites_single_email_persists_and_sends():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=["invitee@example.com"])

    assert len(invites) == 1
    assert invites[0].team == team
    assert invites[0].email == "invitee@example.com"
    assert invites[0].pk is not None
    assert len(djmail.outbox) == 1


def test_create_team_invites_multiple_emails():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=["a@example.com", "b@example.com"])

    assert len(invites) == 2
    assert {i.email for i in invites} == {"a@example.com", "b@example.com"}
    assert all(i.team == team for i in invites)
    assert len(djmail.outbox) == 2


def test_create_team_invites_empty_list_is_noop():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=[])

    assert invites == []
    assert djmail.outbox == []
