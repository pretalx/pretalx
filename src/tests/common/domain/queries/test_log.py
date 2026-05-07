# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.domain.queries.log import actions_by
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_actions_by_filters_by_actor():
    user = UserFactory()
    user.log_action("pretalx.user.test_action")

    actions = actions_by(user)

    assert actions.count() == 1
    assert actions.first().person == user


def test_actions_by_excludes_other_actors():
    user = UserFactory()
    other = UserFactory()
    other.log_action("pretalx.user.test", person=other)

    assert list(actions_by(user)) == []
