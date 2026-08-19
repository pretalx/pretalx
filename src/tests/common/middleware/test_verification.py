# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import resolve

from pretalx.common.middleware.event import EventMiddleware
from pretalx.common.middleware.verification import EmailVerificationMiddleware
from pretalx.person.enums import EmailVerificationState
from tests.factories import EventFactory, UserFactory
from tests.utils import SimpleSession, make_request

pytestmark = pytest.mark.unit

rf = RequestFactory()


def _make_middleware():
    return EmailVerificationMiddleware(lambda request: HttpResponse("ok"))


def _unverified_user():
    return UserFactory(email_verification_state=EmailVerificationState.UNVERIFIED)


@pytest.mark.django_db
def test_gate_redirects_unverified_user_to_event_verification_page(event):
    request = make_request(
        event, user=_unverified_user(), path=f"/{event.slug}/schedule/"
    )

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/verify/"


@pytest.mark.django_db
def test_gate_redirects_user_without_event_to_orga_verification_page():
    request = make_request(None, user=_unverified_user(), path="/orga/event/")

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == "/orga/verify/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_gate_redirect_on_custom_domain_stays_on_that_domain():
    event = EventFactory(custom_domain="http://custom.example.com", is_public=True)
    request = rf.get(f"/{event.slug}/schedule/", headers={"host": "custom.example.com"})
    request.user = _unverified_user()
    request.session = SimpleSession()

    response = EventMiddleware(_make_middleware())(request)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/verify/"


@pytest.mark.django_db
def test_gate_redirects_orga_path_of_custom_domain_event_to_orga_verification():
    event = EventFactory(custom_domain="http://custom.example.com")
    request = make_request(
        event, user=_unverified_user(), path=f"/orga/event/{event.slug}/submissions/"
    )

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == "/orga/verify/"


@pytest.mark.django_db
def test_gate_returns_hx_redirect_for_htmx_requests(event):
    request = make_request(
        event,
        user=_unverified_user(),
        path=f"/{event.slug}/schedule/",
        headers={"HX-Request": "true"},
    )

    response = _make_middleware()(request)

    assert response.status_code == 286
    assert response["HX-Redirect"] == f"/{event.slug}/verify/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    (EmailVerificationState.VERIFIED, EmailVerificationState.LEGACY),
    ids=["verified", "legacy"],
)
def test_gate_passes_proven_and_legacy_accounts(event, state):
    user = UserFactory(email_verification_state=state)
    request = make_request(event, user=user, path=f"/{event.slug}/schedule/")

    response = _make_middleware()(request)

    assert response.content == b"ok"


@pytest.mark.django_db
def test_gate_passes_anonymous_users(event):
    request = make_request(event, user=AnonymousUser(), path=f"/{event.slug}/schedule/")

    response = _make_middleware()(request)

    assert response.content == b"ok"


@pytest.mark.django_db
def test_gate_passes_requests_without_a_user_attribute(event):
    request = rf.get(f"/{event.slug}/schedule/")
    request.session = SimpleSession()

    response = _make_middleware()(request)

    assert response.content == b"ok"


@pytest.mark.parametrize(
    "path",
    (
        "/myevent/verify/",
        "/myevent/logout",
        "/myevent/auth/",
        "/myevent/reset",
        "/myevent/reset/token",
        "/myevent/invite/speaker/token/",
        "/myevent/invite/token",
        "/myevent/invitation/ABCDEF/1",
        "/myevent/submit/",
        "/myevent/submit/tmpid/info/",
        "/myevent/submit/restart-ABCDEF/",
        "/myevent/static/event.css",
        "/myevent/locale/set",
        "/locale/set",
        "/orga/verify/",
        "/orga/logout/",
        "/orga/reset/",
        "/orga/reset/token",
        "/orga/event/myevent/reset/",
        "/orga/event/myevent/reset/token",
        "/orga/invitation/ABCDEF",
        "/redirect/",
        "/redirect/ABCDEF",
        "/api/events/",
    ),
)
def test_exempt_paths_are_reachable_while_unverified(path):
    assert EmailVerificationMiddleware.is_exempt(resolve(path)) is True


@pytest.mark.parametrize(
    "path",
    ("/myevent/", "/myevent/schedule/", "/myevent/me/", "/orga/event/", "/orga/me"),
)
def test_gated_paths_are_not_exempt(path):
    assert EmailVerificationMiddleware.is_exempt(resolve(path)) is False
