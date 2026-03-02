# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.urls import reverse

from pretalx.orga.views.auth import LoginView, RecoverView, ResetView
from tests.factories import EventFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_login_view_event_returns_request_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    assert view.event == event


def test_login_view_event_returns_none_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.event is None


def test_login_view_success_url_with_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    assert view.success_url == event.orga_urls.base


def test_login_view_success_url_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.success_url == reverse("orga:event.list")


def test_login_view_get_form_kwargs_hides_register(event):
    request = make_request(event)
    view = make_view(LoginView, request)
    view.object = None

    kwargs = view.get_form_kwargs()

    assert kwargs["hide_register"] is True


def test_login_view_get_password_reset_link_with_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    expected = reverse("orga:event.auth.reset", kwargs={"event": event.slug})
    assert view.get_password_reset_link() == expected


def test_login_view_get_password_reset_link_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.get_password_reset_link() == reverse("orga:auth.reset")


def test_reset_view_get_success_url_with_event(event):
    request = make_request(event)
    view = make_view(ResetView, request)

    expected = reverse("orga:event.login", kwargs={"event": event.slug})
    assert view.get_success_url() == expected


def test_reset_view_get_success_url_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(ResetView, request)

    assert view.get_success_url() == reverse("orga:login")


def test_recover_view_get_success_url():
    event = EventFactory()
    request = make_request(event)
    view = make_view(RecoverView, request)

    assert view.get_success_url() == reverse("orga:login")


def test_recover_view_get_user_finds_valid_token():
    user = UserFactory()
    user.reset_password(event=None, orga=True)
    user.refresh_from_db()
    event = EventFactory()
    request = make_request(event)
    view = make_view(RecoverView, request, token=user.pw_reset_token)

    assert view.get_user() == user
