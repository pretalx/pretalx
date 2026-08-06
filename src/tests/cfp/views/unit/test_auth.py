# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.http import Http404

from pretalx.cfp.views.auth import LoginView, LogoutView
from tests.factories import EventFactory
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
