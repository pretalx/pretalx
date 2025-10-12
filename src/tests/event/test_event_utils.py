# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.event.models import Organiser
from pretalx.event.utils import create_organiser_with_team


@pytest.mark.django_db
def test_user_organiser_init(user):
    assert Organiser.objects.count() == 0
    assert user.teams.count() == 0
    create_organiser_with_team(name="Name", slug="slug", users=[user])
    assert Organiser.objects.count() == 1
    assert user.teams.count() == 1
    assert user.teams.get().organiser == Organiser.objects.get()
