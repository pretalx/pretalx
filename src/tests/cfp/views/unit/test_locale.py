# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.http import QueryDict

from pretalx.cfp.views.locale import LocaleSet
from tests.factories import UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_locale_set_redirects_to_root_without_next(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "en"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert response.status_code == 302
    assert response.url == "/"


def test_locale_set_sets_cookie_for_valid_locale(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"


def test_locale_set_does_not_set_cookie_for_invalid_locale(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "xx"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert settings.LANGUAGE_COOKIE_NAME not in response.cookies


def test_locale_set_saves_locale_for_authenticated_user(event):
    """LocaleSet persists locale to user model for authenticated users."""
    user = UserFactory(locale="en")
    request = make_request(event, user=user)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    view.get(request)

    user.refresh_from_db()
    assert user.locale == "de"


def test_locale_set_does_not_save_locale_for_anonymous(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)
    assert response.status_code == 302
