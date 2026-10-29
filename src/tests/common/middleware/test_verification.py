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
def test_gate_routes_event_slug_starting_with_orga_to_cfp_verification():
    event = EventFactory(slug="orgacon", is_public=True)
    request = make_request(event, user=_unverified_user(), path="/orgacon/me/")

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == "/orgacon/verify/"


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
    assert "verification_next" not in request.session


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path", "stored", "expected"),
    (
        ("get", "/{slug}/schedule/?day=2", {}, "/{slug}/schedule/?day=2"),
        ("post", "/{slug}/me/", {}, None),
        (
            "get",
            "/{slug}/me/",
            {"verification_next": "/{slug}/me/#section"},
            "/{slug}/me/#section",
        ),
        (
            "get",
            "/{slug}/me/",
            {"verification_next": "/{slug}/schedule/#talk"},
            "/{slug}/me/",
        ),
    ),
    ids=(
        "stores_get_destination",
        "skips_post",
        "keeps_fragment_stored_at_login",
        "overwrites_other_page",
    ),
)
def test_gate_stores_destination_for_redirect_after_verification(
    event, method, path, stored, expected
):
    request = make_request(
        event, user=_unverified_user(), method=method, path=path.format(slug=event.slug)
    )
    request.session.update(
        {key: value.format(slug=event.slug) for key, value in stored.items()}
    )

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert request.session.get("verification_next") == (
        expected and expected.format(slug=event.slug)
    )


@pytest.mark.django_db
def test_gate_does_not_store_unsafe_destination(event):
    request = make_request(event, user=_unverified_user(), path=f"/{event.slug}/me/")
    request.path = "//evil.example.com/"

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert "verification_next" not in request.session


@pytest.mark.django_db
@pytest.mark.parametrize(
    "make_user",
    (
        lambda: UserFactory(email_verification_state=EmailVerificationState.VERIFIED),
        lambda: UserFactory(email_verification_state=EmailVerificationState.LEGACY),
        AnonymousUser,
    ),
    ids=["verified", "legacy", "anonymous"],
)
def test_gate_passes_proven_legacy_and_anonymous_accounts(event, make_user):
    request = make_request(event, user=make_user(), path=f"/{event.slug}/schedule/")

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
