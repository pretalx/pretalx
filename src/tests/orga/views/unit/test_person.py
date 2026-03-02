# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.api.versions import CURRENT_VERSION
from pretalx.common.ui import Button
from pretalx.orga.views.person import PreferencesView, UserSettings
from pretalx.person.forms import AuthTokenForm, LoginInfoForm, OrgaProfileForm
from tests.factories import UserApiTokenFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_user_settings_get_success_url(event):
    request = make_request(event, user=UserFactory())
    view = make_view(UserSettings, request)

    assert view.get_success_url() == "/orga/me"


@pytest.mark.parametrize(
    ("form_attr", "expected_class"),
    (
        ("login_form", LoginInfoForm),
        ("profile_form", OrgaProfileForm),
        ("token_form", AuthTokenForm),
    ),
)
def test_user_settings_form_unbound_on_get(event, form_attr, expected_class):
    request = make_request(event, user=UserFactory())
    view = make_view(UserSettings, request)

    form = getattr(view, form_attr)

    assert isinstance(form, expected_class)
    assert not form.is_bound


@pytest.mark.parametrize(
    ("form_name", "expected_class"),
    (("login", LoginInfoForm), ("profile", OrgaProfileForm), ("token", AuthTokenForm)),
)
def test_user_settings_form_bound_on_post(event, form_name, expected_class):
    request = make_request(event, user=UserFactory(), method="post")
    request.POST = {"form": form_name}
    view = make_view(UserSettings, request)

    form = getattr(view, f"{form_name}_form")

    assert isinstance(form, expected_class)
    assert form.is_bound


def test_user_settings_current_version(event):
    request = make_request(event, user=UserFactory())
    view = make_view(UserSettings, request)

    assert view.current_version() == CURRENT_VERSION


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


def test_user_settings_get_context_data_has_submit_buttons(event):
    request = make_request(event, user=UserFactory())
    view = make_view(UserSettings, request)
    view.kwargs = {}

    context = view.get_context_data()

    assert len(context["profile_submit"]) == 1
    assert isinstance(context["profile_submit"][0], Button)
    assert context["profile_submit"][0].value == "profile"
    assert len(context["login_submit"]) == 1
    assert context["login_submit"][0].value == "login"
    assert len(context["token_submit"]) == 1
    assert context["token_submit"][0].value == "token"


def test_preferences_view_permission_required():
    assert PreferencesView.permission_required == "event.orga_access_event"
