# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.middleware.csrf import CSRF_SESSION_KEY
from django.test import RequestFactory, override_settings

from pretalx.common.middleware.domains import (
    CsrfViewMiddleware,
    SessionMiddleware,
    get_cookie_domain,
)

pytestmark = pytest.mark.unit

rf = RequestFactory()


def dummy_response(request):
    return HttpResponse("ok")


@override_settings(SITE_NETLOC="testserver")
def test_get_cookie_domain_returns_none_when_host_has_no_dot():
    request = rf.get("/")
    request.host = "localhost"

    assert get_cookie_domain(request) is None


@override_settings(
    SITE_NETLOC="testserver.com", SESSION_COOKIE_DOMAIN=".testserver.com"
)
def test_get_cookie_domain_returns_configured_domain_on_default_host():
    request = rf.get("/")
    request.host = "testserver.com"

    assert get_cookie_domain(request) == ".testserver.com"


@override_settings(
    SITE_NETLOC="testserver.com", SESSION_COOKIE_DOMAIN=".testserver.com"
)
def test_get_cookie_domain_returns_none_on_custom_domain():
    request = rf.get("/")
    request.host = "custom.example.com"

    assert get_cookie_domain(request) is None


@pytest.mark.parametrize(
    ("host", "expected_domain"),
    (("testserver.com", ".testserver.com"), ("custom.example.com", "")),
)
@pytest.mark.django_db
@override_settings(
    SITE_NETLOC="testserver.com", SESSION_COOKIE_DOMAIN=".testserver.com"
)
def test_session_middleware_sets_correct_cookie_domain(host, expected_domain):

    def view(request):
        request.session["key"] = "value"
        return HttpResponse("ok")

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = host

    response = middleware(request)

    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert cookie["domain"] == expected_domain


@pytest.mark.django_db
def test_session_middleware_deletes_cookie_when_session_empty():
    def view(request):
        request.session.flush()
        return HttpResponse("ok")

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = "localhost"
    request.COOKIES[settings.SESSION_COOKIE_NAME] = "old-session-id"

    response = middleware(request)

    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert cookie["max-age"] == 0


@pytest.mark.django_db
def test_session_middleware_patches_vary_header_when_session_accessed():
    def view(request):
        _ = request.session.get("anything")
        return HttpResponse("ok")

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = "localhost"

    response = middleware(request)

    assert response["Vary"] == "Cookie"


@pytest.mark.django_db
def test_session_middleware_skips_save_on_500_response():
    def view(request):
        request.session["key"] = "value"
        return HttpResponse("error", status=500)

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = "localhost"

    response = middleware(request)

    assert response.status_code == 500
    assert settings.SESSION_COOKIE_NAME not in response.cookies


@pytest.mark.parametrize(
    ("host", "expected_domain"),
    (("testserver.com", ".testserver.com"), ("custom.example.com", "")),
)
@pytest.mark.django_db
@override_settings(
    SITE_NETLOC="testserver.com",
    SESSION_COOKIE_DOMAIN=".testserver.com",
    CSRF_USE_SESSIONS=False,
)
def test_csrf_middleware_set_csrf_cookie_sets_correct_domain(host, expected_domain):
    middleware = CsrfViewMiddleware(dummy_response)
    request = rf.get("/")
    request.host = host
    request.META["CSRF_COOKIE"] = "test-csrf-token"

    response = HttpResponse()
    middleware._set_csrf_cookie(request, response)

    cookie = response.cookies.get(settings.CSRF_COOKIE_NAME)
    assert cookie is not None
    assert cookie["domain"] == expected_domain
    assert cookie.value == "test-csrf-token"


@pytest.mark.django_db
@override_settings(CSRF_USE_SESSIONS=True)
def test_csrf_middleware_stores_token_in_session_when_configured():
    middleware = CsrfViewMiddleware(dummy_response)
    request = rf.get("/")
    request.host = "testserver.com"
    request.session = SessionStore()
    request.META["CSRF_COOKIE"] = "test-csrf-token"

    response = HttpResponse()
    middleware._set_csrf_cookie(request, response)

    assert request.session[CSRF_SESSION_KEY] == "test-csrf-token"
    assert "csrftoken" not in response.cookies


@pytest.mark.django_db
@override_settings(CSRF_USE_SESSIONS=True)
def test_csrf_middleware_skips_session_write_when_token_unchanged():
    middleware = CsrfViewMiddleware(dummy_response)
    request = rf.get("/")
    request.host = "testserver.com"
    request.session = SessionStore()
    request.session[CSRF_SESSION_KEY] = "same-token"
    request.session.save()
    request.session.modified = False
    request.META["CSRF_COOKIE"] = "same-token"

    response = HttpResponse()
    middleware._set_csrf_cookie(request, response)

    assert request.session[CSRF_SESSION_KEY] == "same-token"
    assert not request.session.modified


@pytest.mark.django_db
@override_settings(SESSION_SAVE_EVERY_REQUEST=True)
def test_session_middleware_saves_every_request_without_access():
    middleware = SessionMiddleware(dummy_response)
    request = rf.get("/")
    request.host = "localhost"

    response = middleware(request)

    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert response.get("Vary") is None


def test_session_middleware_process_response_without_session_attribute():
    middleware = SessionMiddleware(dummy_response)
    request = rf.get("/")
    request.host = "localhost"
    response = HttpResponse("ok")

    result = middleware.process_response(request, response)

    assert result.content == b"ok"
    assert settings.SESSION_COOKIE_NAME not in result.cookies


@pytest.mark.django_db
@override_settings(SESSION_SAVE_EVERY_REQUEST=True)
def test_session_middleware_sets_browser_close_cookie_without_max_age():

    def view(request):
        request.session.set_expiry(0)
        request.session["key"] = "value"
        return HttpResponse("ok")

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = "localhost"

    response = middleware(request)

    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert cookie["max-age"] == ""
    assert cookie["expires"] == ""


@pytest.mark.django_db
def test_session_middleware_creates_new_session_on_update_error():
    save_call_count = 0
    middleware = SessionMiddleware(dummy_response)
    request = rf.get("/")
    request.host = "localhost"

    # Run through middleware to initialise the session
    middleware.process_request(request)
    request.session["key"] = "value"

    # Patch save to raise UpdateError on first call only
    original_save = request.session.save

    def failing_save(*args, **kwargs):
        nonlocal save_call_count
        save_call_count += 1
        if save_call_count == 1:
            raise UpdateError
        return original_save(*args, **kwargs)

    request.session.save = failing_save
    response = HttpResponse("ok")

    result = middleware.process_response(request, response)

    cookie = result.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert cookie.value != ""
