import pytest
from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import DisallowedHost
from django.http import Http404, HttpResponse
from django.middleware.csrf import CSRF_SESSION_KEY
from django.test import RequestFactory, override_settings

from pretalx.common.middleware.domains import (
    CsrfViewMiddleware,
    MultiDomainMiddleware,
    SessionMiddleware,
    get_cookie_domain,
)
from tests.factories import EventFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


def dummy_response(request):
    return HttpResponse("ok")


@override_settings(SITE_NETLOC="testserver")
def test_get_cookie_domain_returns_none_when_host_has_no_dot():
    """Browsers reject cookie domains without dots (e.g. 'localhost')."""
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
    """On custom domains we must not leak cookies to other sites."""
    request = rf.get("/")
    request.host = "custom.example.com"

    assert get_cookie_domain(request) is None


def test_multi_domain_middleware_get_host_from_host_header():
    request = rf.get("/")
    request.META["HTTP_HOST"] = "example.com"

    assert MultiDomainMiddleware.get_host(request) == "example.com"


@pytest.mark.parametrize(
    ("use_forwarded", "expected"),
    ((True, "public.example.com"), (False, "example.com")),
)
def test_multi_domain_middleware_get_host_respects_x_forwarded_host_setting(
    use_forwarded, expected
):
    with override_settings(USE_X_FORWARDED_HOST=use_forwarded):
        request = rf.get("/")
        request.META["HTTP_HOST"] = "example.com"
        request.META["HTTP_X_FORWARDED_HOST"] = "public.example.com"

        assert MultiDomainMiddleware.get_host(request) == expected


@pytest.mark.parametrize(
    ("port", "scheme", "expected"),
    (
        ("80", "http", "fallback.example.com"),
        ("8080", "http", "fallback.example.com:8080"),
        ("443", "https", "fallback.example.com"),
    ),
)
def test_multi_domain_middleware_get_host_reconstructs_from_server_name(
    port, scheme, expected
):
    """When no Host headers are present, reconstruct from SERVER_NAME/SERVER_PORT (PEP 333)."""
    request = rf.get("/")
    request.META.pop("HTTP_HOST", None)
    request.META["SERVER_NAME"] = "fallback.example.com"
    request.META["SERVER_PORT"] = port
    request.META["wsgi.url_scheme"] = scheme

    assert MultiDomainMiddleware.get_host(request) == expected


@pytest.mark.parametrize("path", ("/robots.txt", "/redirect/", "/api/events/"))
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_allows_any_domain_for_special_paths(
    path,
):
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(path)
    request.META["HTTP_HOST"] = "random.example.com"
    request.META["SERVER_NAME"] = "random.example.com"

    result = middleware.process_request(request)

    assert result is None


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_on_default_domain():
    event = EventFactory()
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "testserver"

    result = middleware.process_request(request)

    assert result is None
    assert request.event == event
    assert request.uses_custom_domain is False


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_nonexistent_event_raises_404():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/no-such-event/")
    request.META["HTTP_HOST"] = "testserver"

    with pytest.raises(Http404):
        middleware.process_request(request)


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_custom_domain_match():
    """When the request domain matches the event's custom domain, mark it."""
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "custom.example.com"

    result = middleware.process_request(request)

    assert result is None
    assert request.event == event
    assert request.uses_custom_domain is True


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_custom_domain_redirects_from_default():
    """On the default domain, public event pages redirect to the custom domain."""
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "testserver"

    result = middleware.process_request(request)

    assert result.status_code == 302
    assert result.url == f"https://custom.example.com/{event.slug}/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_custom_domain_no_redirect_for_orga():
    """Organiser pages stay on the default domain even when a custom domain is set."""
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/orga/event/{event.slug}/")
    request.META["HTTP_HOST"] = "testserver"

    result = middleware.process_request(request)

    assert result is None


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_wrong_domain_raises_404():
    """An event page on a wrong domain raises 404 to avoid info leakage."""
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "wrong.example.com"

    with pytest.raises(Http404):
        middleware.process_request(request)


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_event_no_custom_domain_wrong_host_raises_404():
    """Event without custom domain on a non-default domain raises 404."""
    event = EventFactory()
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "other.example.com"
    request.META["SERVER_NAME"] = "other.example.com"

    with pytest.raises(Http404):
        middleware.process_request(request)


@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_process_request_default_domain_no_event():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/redirect/")
    request.META["HTTP_HOST"] = "testserver"

    result = middleware.process_request(request)

    assert result is None


@override_settings(SITE_NETLOC="testserver.com", DEBUG=True)
def test_multi_domain_middleware_process_request_debug_mode_allows_any_domain():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/400")
    request.META["HTTP_HOST"] = "anything.example.com"
    request.META["SERVER_NAME"] = "anything.example.com"

    result = middleware.process_request(request)

    assert result is None


@pytest.mark.parametrize("host", ("localhost", "127.0.0.1", "testserver"))
@override_settings(SITE_NETLOC="production.example.com", DEBUG=False)
def test_multi_domain_middleware_process_request_local_hosts_always_allowed(host):
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/400")
    request.META["HTTP_HOST"] = host
    request.META["SERVER_NAME"] = host

    result = middleware.process_request(request)

    assert result is None


@override_settings(
    SITE_NETLOC="testserver.com", SITE_URL="https://testserver.com", DEBUG=False
)
def test_multi_domain_middleware_process_request_orga_on_unknown_domain_redirects_to_site_url():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/orga/login/")
    request.META["HTTP_HOST"] = "unknown.example.com"
    request.META["SERVER_NAME"] = "unknown.example.com"

    result = middleware.process_request(request)

    assert result.status_code == 302
    assert result.url == "https://testserver.com/orga/login/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_multi_domain_middleware_process_request_custom_domain_redirects_to_public_event():
    """A non-event page on a custom domain redirects to the most recent public event."""
    event = EventFactory(custom_domain="http://custom.example.com", is_public=True)
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/400")
    request.META["HTTP_HOST"] = "custom.example.com"
    request.META["SERVER_NAME"] = "custom.example.com"

    result = middleware.process_request(request)

    assert result.status_code == 302
    assert result.url == f"http://custom.example.com/{event.slug}/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_multi_domain_middleware_process_request_custom_domain_no_public_event_returns_none():
    """A custom domain with only non-public events returns None (shows start page)."""
    EventFactory(custom_domain="http://custom.example.com", is_public=False)
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/400")
    request.META["HTTP_HOST"] = "custom.example.com"
    request.META["SERVER_NAME"] = "custom.example.com"

    result = middleware.process_request(request)

    assert result is None


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_multi_domain_middleware_process_request_unknown_domain_raises_disallowed_host():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/400")
    request.META["HTTP_HOST"] = "unknown.example.com"
    request.META["SERVER_NAME"] = "unknown.example.com"

    with pytest.raises(DisallowedHost):
        middleware.process_request(request)


@pytest.mark.django_db
def test_multi_domain_middleware_process_response_adds_csp_for_orga_with_custom_domain():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/orga/event/{event.slug}/")
    request.event = event
    response = HttpResponse()

    result = middleware.process_response(request, response)

    assert result._csp_update["form-action"] == [event.urls.base.full()]


def test_multi_domain_middleware_process_response_no_csp_without_event():
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/orga/login/")
    response = HttpResponse()

    result = middleware.process_response(request, response)

    assert not hasattr(result, "_csp_update")


@pytest.mark.django_db
def test_multi_domain_middleware_process_response_no_csp_without_custom_domain():
    event = EventFactory()
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/orga/event/{event.slug}/")
    request.event = event
    response = HttpResponse()

    result = middleware.process_response(request, response)

    assert not hasattr(result, "_csp_update")


@pytest.mark.django_db
def test_multi_domain_middleware_process_response_no_csp_for_non_orga():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.event = event
    response = HttpResponse()

    result = middleware.process_response(request, response)

    assert not hasattr(result, "_csp_update")


@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_call_returns_redirect_from_process_request():
    """When process_request returns a redirect, __call__ returns it directly."""
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get("/orga/login/")
    request.META["HTTP_HOST"] = "unknown.example.com"
    request.META["SERVER_NAME"] = "unknown.example.com"

    response = middleware(request)

    assert response.status_code == 302


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_multi_domain_middleware_call_passes_through_to_view():
    event = EventFactory()
    middleware = MultiDomainMiddleware(dummy_response)
    request = rf.get(f"/{event.slug}/")
    request.META["HTTP_HOST"] = "testserver"

    response = middleware(request)

    assert response.content == b"ok"


@pytest.mark.parametrize(
    ("host", "expected_domain"),
    (("testserver.com", ".testserver.com"), ("custom.example.com", "")),
)
@pytest.mark.django_db
@override_settings(
    SITE_NETLOC="testserver.com", SESSION_COOKIE_DOMAIN=".testserver.com"
)
def test_session_middleware_sets_correct_cookie_domain(host, expected_domain):
    """On custom domains, cookie domain is empty to prevent leaking to other sites."""

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
    """When the CSRF token already matches what's in the session, don't write."""
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
    """With SESSION_SAVE_EVERY_REQUEST, session is saved even when not accessed
    by the view, and the Vary header is not added."""

    def view(request):
        return HttpResponse("ok")

    middleware = SessionMiddleware(view)
    request = rf.get("/")
    request.host = "localhost"

    response = middleware(request)

    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None
    assert response.get("Vary") is None


def test_session_middleware_process_response_without_session_attribute():
    """When request has no session (e.g. middleware short-circuited), response passes through."""
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
    """When session expires at browser close, cookie has no max-age/expires."""

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
    """When session.save() raises UpdateError (concurrent modification),
    a new session is created instead."""
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
