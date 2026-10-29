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


@pytest.mark.parametrize(
    ("is_admin", "in_team", "all_events", "limit", "expected_limit", "expired"),
    (
        (False, True, False, [0, 1], [0], False),
        (False, False, False, [0], [], True),
        (False, False, True, [], [], True),
        (True, False, True, [], [], False),
        (True, False, False, [0], [0], False),
        (False, True, True, [], [], False),
        (False, True, False, [0], [0], False),
    ),
    ids=[
        "removes_inaccessible",
        "expires_when_all_removed",
        "expires_all_events_without_access",
        "keeps_administrator_all_events",
        "keeps_administrator_limit_events",
        "keeps_all_events_with_access",
        "noop_when_all_accessible",
    ],
)
def test_update_token_events(
    is_admin, in_team, all_events, limit, expected_limit, expired
):
    user = UserFactory(is_administrator=is_admin)
    events = [EventFactory(), EventFactory()]
    team = TeamFactory(organiser=events[0].organiser, all_events=True)
    team.members.set([user] if in_team else [])
    token = UserApiTokenFactory(user=user, all_events=all_events, expires=None)
    token.limit_events.add(*[events[index] for index in limit])

    update_token_events(token)

    token.refresh_from_db()
    assert list(token.limit_events.all()) == [events[index] for index in expected_limit]
    assert (token.expires is not None and token.expires <= tz_now()) is expired


def test_upgrade_token_sets_current_version_and_logs():
    user = UserFactory()
    token = UserApiTokenFactory(user=user, version="v1")

    upgrade_token(token)

    token.refresh_from_db()
    assert token.version == CURRENT_VERSION
    log_entry = (
        token.logged_actions().filter(action_type="pretalx.user.token.upgrade").get()
    )
    assert log_entry.person == user


def test_revoke_token_expires_and_logs():
    user = UserFactory()
    token = UserApiTokenFactory(user=user, expires=None)

    revoke_token(token)

    token.refresh_from_db()
    assert token.expires is not None
    assert token.expires <= tz_now()
    assert not token.is_active
    log_entry = (
        token.logged_actions().filter(action_type="pretalx.user.token.revoke").get()
    )
    assert log_entry.person == user
    assert log_entry.data["token"] == f"{token.token[:4]}…"
