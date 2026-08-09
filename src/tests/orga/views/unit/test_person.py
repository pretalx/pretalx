# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import Http404

from pretalx.orga.views.person import TokenEdit, UserSettings
from tests.factories import UserApiTokenFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("form_name", ("login", "profile", "token"))
def test_user_settings_binds_only_the_submitted_form(event, form_name):
    request = make_request(event, user=UserFactory(), method="post")
    request.POST = {"form": form_name}
    view = make_view(UserSettings, request)

    bound = {
        name
        for name in ("login", "profile", "token")
        if getattr(view, f"{name}_form").is_bound
    }

    assert bound == {form_name}


def test_user_settings_forms_unbound_on_get(event):
    request = make_request(event, user=UserFactory())
    view = make_view(UserSettings, request)

    bound = {
        name
        for name in ("login", "profile", "token")
        if getattr(view, f"{name}_form").is_bound
    }

    assert bound == set()


def test_user_settings_tokens_returns_user_tokens(event):
    user = UserFactory()
    token = UserApiTokenFactory(user=user)
    request = make_request(event, user=user)
    view = make_view(UserSettings, request)

    assert list(view.tokens) == [token]


def test_user_settings_tokens_excludes_other_users(event):
    user = UserFactory()
    UserApiTokenFactory()  # token for a different user
    request = make_request(event, user=user)
    view = make_view(UserSettings, request)

    assert list(view.tokens) == []


def test_token_edit_token_404_for_other_users_token(event):
    user = UserFactory()
    other_token = UserApiTokenFactory()
    request = make_request(event, user=user)
    view = make_view(TokenEdit, request, pk=other_token.pk)

    with pytest.raises(Http404):
        view.get_object()
