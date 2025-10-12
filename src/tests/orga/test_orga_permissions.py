# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.auth.models import AnonymousUser

from pretalx.event.rules import (
    can_change_event_settings,
    can_change_organiser_settings,
    can_change_teams,
)


def test_permissions_change_event_doesnt_crash_on_unexpected_values():
    assert can_change_event_settings(None, None) is False
    assert can_change_event_settings(AnonymousUser, None) is False


@pytest.mark.django_db
def test_permissions_change_organiser_takes_event(orga_user, event):
    assert can_change_organiser_settings(orga_user, event) is True


@pytest.mark.django_db
def test_create_organiser_orga_user(orga_user):
    assert can_change_organiser_settings(orga_user, None) is False


@pytest.mark.django_db
def test_create_organiser_administrator(administrator):
    assert can_change_organiser_settings(administrator, None) is True


def test_permissions_change_teams_doesnt_crash_on_unexpected_values():
    assert can_change_teams(None, None) is False
    assert can_change_teams(AnonymousUser, None) is False
