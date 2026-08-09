# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils.timezone import now

from pretalx.orga.views.auth import RecoverView
from tests.factories import EventFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_recover_view_get_user_finds_user_for_token():
    user = UserFactory(pw_reset_token="validtoken", pw_reset_time=now())
    UserFactory(pw_reset_token="othertoken", pw_reset_time=now())
    request = make_request(EventFactory())
    view = make_view(RecoverView, request, token="validtoken")

    assert view.get_user() == user
