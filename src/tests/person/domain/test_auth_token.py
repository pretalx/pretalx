# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.utils.timezone import now as tz_now

from pretalx.api.versions import CURRENT_VERSION
from pretalx.person.domain.auth_token import (
    revoke_token,
    update_token_events,
    upgrade_token,
)
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_update_token_events_removes_inaccessible():
    """When a user loses team access, events they can no longer reach are removed."""
    user = UserFactory()
    event1 = EventFactory()
    event2 = EventFactory()
    team = TeamFactory(organiser=event1.organiser, all_events=True)
    team.members.add(user)
    # event2 is on a different organiser, so user has no access
    token = UserApiTokenFactory(user=user)
    token.events.add(event1, event2)

    update_token_events(token)

    assert list(token.events.all()) == [event1]


def test_update_token_events_expires_when_all_removed():
    """Token is expired when all events are removed."""
    user = UserFactory()
    event = EventFactory()
    # User has no team membership, so no access to any events
    token = UserApiTokenFactory(user=user, expires=None)
    token.events.add(event)

    update_token_events(token)

    token.refresh_from_db()
    assert not token.events.exists()
    assert token.expires is not None
    assert token.expires <= tz_now()


def test_update_token_events_noop_when_all_accessible():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)
    token = UserApiTokenFactory(user=user)
    token.events.add(event)

    update_token_events(token)

    assert list(token.events.all()) == [event]
    token.refresh_from_db()
    assert token.expires is None


def test_upgrade_token_sets_current_version_and_logs():
    user = UserFactory()
    token = UserApiTokenFactory(user=user, version="LEGACY")

    upgrade_token(token)

    token.refresh_from_db()
    assert token.version == CURRENT_VERSION
    assert (
        user.logged_actions().filter(action_type="pretalx.user.token.upgrade").exists()
    )


def test_revoke_token_expires_and_logs():
    user = UserFactory()
    token = UserApiTokenFactory(user=user, expires=None)

    revoke_token(token)

    token.refresh_from_db()
    assert token.expires is not None
    assert token.expires <= tz_now()
    assert not token.is_active
    assert (
        user.logged_actions().filter(action_type="pretalx.user.token.revoke").exists()
    )
