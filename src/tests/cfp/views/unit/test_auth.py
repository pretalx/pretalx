# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404
from django.utils.timezone import now

from pretalx.cfp.views.auth import LoginView, LogoutView, RecoverView
from tests.factories import EventFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_logout_view_get_redirects_to_event_start(event):
    request = make_request(event)
    view = make_view(LogoutView, request)

    response = view.get(request)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/cfp"


def test_login_view_dispatch_raises_404_when_event_not_public():
    event = EventFactory(is_public=False)
    request = make_request(event)

    with pytest.raises(Http404):
        LoginView.as_view()(request, event=event.slug)


def test_login_view_get_error_url_returns_event_base(event):
    request = make_request(event)
    view = make_view(LoginView, request, event=event.slug)

    assert view.get_error_url() == event.urls.base


@pytest.mark.parametrize(("is_invite", "expected"), ((False, False), (True, True)))
def test_recover_view_is_invite_template(event, is_invite, expected):
    user = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())
    request = make_request(event)
    view = make_view(RecoverView, request, token="validtoken123", event=event.slug)
    view.user = user
    view.is_invite = is_invite

    assert view.is_invite_template() is expected
