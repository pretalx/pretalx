# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import DisallowedHost
from django.http import Http404, HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import Resolver404
from django.utils import translation

from pretalx.common.middleware.event import EventMiddleware
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit

rf = RequestFactory()


def _make_middleware():
    response = HttpResponse("ok")

    def get_response(request):
        return response

    return EventMiddleware(get_response)


@pytest.mark.django_db
def test_handle_orga_url_redirects_custom_domain_to_site_url(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.uses_custom_domain = True
    request.user = UserFactory()

    response = middleware._handle_orga_url(
        request, SimpleNamespace(url_name="event.dashboard")
    )

    assert response.status_code == 302
    assert response.url.startswith(settings.SITE_URL)


@pytest.mark.django_db
def test_handle_orga_url_redirects_anonymous_to_login(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.uses_custom_domain = False
    request.user = AnonymousUser()
    request.event = event

    response = middleware._handle_orga_url(
        request, SimpleNamespace(url_name="event.dashboard")
    )

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.parametrize("url_name", EventMiddleware.UNAUTHENTICATED_ORGA_URLS)
def test_handle_orga_url_allows_anonymous_on_exempt_urls(url_name):
    middleware = _make_middleware()
    request = rf.get("/orga/login/")
    request.uses_custom_domain = False
    request.user = AnonymousUser()

    result = middleware._handle_orga_url(request, SimpleNamespace(url_name=url_name))

    assert result is None


@pytest.mark.django_db
def test_handle_orga_url_allows_authenticated_user():
    middleware = _make_middleware()
    request = rf.get("/orga/")
    request.uses_custom_domain = False
    request.user = UserFactory()

    result = middleware._handle_orga_url(
        request, SimpleNamespace(url_name="event.dashboard")
    )

    assert result is None


@pytest.mark.django_db
def test_select_locale_uses_event_locales_when_available(event):
    middleware = _make_middleware()
    request = rf.get("/")
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE in event.locales


@pytest.mark.django_db
def test_select_locale_sets_timezone_from_event(event):
    middleware = _make_middleware()
    request = rf.get("/")
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.timezone == event.timezone


@pytest.mark.django_db
def test_select_locale_sets_timezone_from_authenticated_user_without_event():
    middleware = _make_middleware()
    user = UserFactory(timezone="Europe/Berlin")
    request = rf.get("/")
    request.event = None
    request.user = user
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.timezone == "Europe/Berlin"


def test_select_locale_sets_timezone_from_settings_for_anonymous_without_event():
    middleware = _make_middleware()
    request = rf.get("/")
    request.event = None
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.timezone == settings.TIME_ZONE


@pytest.mark.django_db
def test_select_locale_query_param_takes_priority():
    middleware = _make_middleware()
    event = EventFactory(locales=["en", "de"])
    request = rf.get("/", {"lang": "de"})
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == "de"


@pytest.mark.django_db
def test_select_locale_user_locale_over_cookie():
    middleware = _make_middleware()
    event = EventFactory(locales=["en", "de"])
    user = UserFactory(locale="de")
    request = rf.get("/")
    request.event = event
    request.user = user
    request.COOKIES = {settings.LANGUAGE_COOKIE_NAME: "en"}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == "de"


@pytest.mark.django_db
def test_select_locale_cookie_over_browser():
    middleware = _make_middleware()
    event = EventFactory(locales=["en", "de"])
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE="en;q=1.0")
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {settings.LANGUAGE_COOKIE_NAME: "de"}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == "de"


def test_select_locale_falls_back_to_settings_language_code():
    middleware = _make_middleware()
    request = rf.get("/")
    request.event = None
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == settings.LANGUAGE_CODE


@pytest.mark.django_db
def test_call_sets_event_on_request(event):
    assert event.custom_domain is None
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert request.event == event
    assert response.status_code == 200


def _cfp_request(event, user):
    request = rf.get(f"/{event.slug}/")
    request.user = user
    request.COOKIES = {}
    return request


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    (SubmissionStates.SUBMITTED, SubmissionStates.DRAFT),
    ids=("submitted", "draft"),
)
def test_call_annotates_has_cfp_submissions_for_speaker(state):
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    SpeakerRoleFactory(
        submission=SubmissionFactory(event=event, state=state), speaker=speaker
    )

    request = _cfp_request(event, speaker.user)
    _make_middleware()(request)

    assert request.event.has_cfp_submissions is True


@pytest.mark.django_db
def test_call_annotates_has_cfp_submissions_false_for_non_speaker():
    event = EventFactory()
    other_speaker = SpeakerFactory(event=event)
    SpeakerRoleFactory(submission=SubmissionFactory(event=event), speaker=other_speaker)

    request = _cfp_request(event, UserFactory())
    _make_middleware()(request)

    assert request.event.has_cfp_submissions is False


@pytest.mark.django_db
def test_call_does_not_annotate_has_cfp_submissions_for_anonymous():
    event = EventFactory()

    request = _cfp_request(event, AnonymousUser())
    _make_middleware()(request)

    assert not hasattr(request.event, "has_cfp_submissions")


@pytest.mark.django_db
def test_call_does_not_annotate_has_cfp_submissions_on_orga_path():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    SpeakerRoleFactory(submission=SubmissionFactory(event=event), speaker=speaker)

    request = rf.get(f"/orga/event/{event.slug}/")
    request.user = speaker.user
    request.COOKIES = {}
    _make_middleware()(request)

    assert not hasattr(request.event, "has_cfp_submissions")


@pytest.mark.django_db
def test_call_sets_organiser_on_request(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/organiser/{event.organiser.slug}/")
    request.user = UserFactory()
    request.COOKIES = {}

    middleware(request)

    assert request.organiser == event.organiser


@pytest.mark.django_db
def test_call_uppercase_url_slug_resolves_event():
    event = EventFactory()

    request = rf.get(f"/{event.slug.upper()}/")
    request.user = UserFactory()
    request.COOKIES = {}
    _make_middleware()(request)

    assert request.event == event
    assert request.event.has_cfp_submissions is False


@pytest.mark.django_db
def test_call_unknown_event_raises_404():
    middleware = _make_middleware()
    request = rf.get("/nonexistent-event-slug/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    with pytest.raises(Http404):
        middleware(request)


@pytest.mark.django_db
def test_call_event_with_custom_domain_redirects_from_main_domain():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert response.url == f"https://custom.example.com/{event.slug}/"


@pytest.mark.django_db
def test_call_orga_url_on_custom_domain_redirects_to_site_url():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.META["HTTP_HOST"] = "custom.example.com"
    request.user = UserFactory()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert response.url.startswith(settings.SITE_URL)


@pytest.mark.django_db
def test_call_orga_url_anonymous_redirects_to_login(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_call_api_path_exempt_from_custom_domain_redirect_gets_cors_header():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = _make_middleware()
    request = rf.get(f"/api/events/{event.slug}/submissions/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_call_activates_translation(event):
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware(request)

    assert request.LANGUAGE_CODE in event.locales
    assert translation.get_language() == request.LANGUAGE_CODE


@pytest.mark.django_db
def test_call_without_event_passes_through():
    middleware = _make_middleware()
    request = rf.get("/orga/login/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_call_disabled_plugin_raises_404(event):
    assert "tests.dummy_app" not in event.plugin_list
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/test-plugin/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    with pytest.raises(Http404):
        middleware(request)


@pytest.mark.django_db
def test_call_enabled_plugin_passes_through():
    event = EventFactory(plugins="dummy_app")
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/test-plugin/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200


def _domain_request(path, host, user=None):
    request = rf.get(path)
    request.META["HTTP_HOST"] = host
    request.META["SERVER_NAME"] = host
    if user is not None:
        request.user = user
    request.COOKIES = {}
    return request


def test_get_host_from_host_header():
    request = rf.get("/")
    request.META["HTTP_HOST"] = "example.com"

    assert EventMiddleware.get_host(request) == "example.com"


@pytest.mark.parametrize(
    ("use_forwarded", "expected"),
    ((True, "public.example.com"), (False, "example.com")),
)
def test_get_host_respects_x_forwarded_host_setting(use_forwarded, expected):
    with override_settings(USE_X_FORWARDED_HOST=use_forwarded):
        request = rf.get("/")
        request.META["HTTP_HOST"] = "example.com"
        request.META["HTTP_X_FORWARDED_HOST"] = "public.example.com"

        assert EventMiddleware.get_host(request) == expected


@pytest.mark.parametrize(
    ("port", "scheme", "expected"),
    (
        ("80", "http", "fallback.example.com"),
        ("8080", "http", "fallback.example.com:8080"),
        ("443", "https", "fallback.example.com"),
    ),
)
def test_get_host_reconstructs_from_server_name(port, scheme, expected):
    request = rf.get("/")
    request.META.pop("HTTP_HOST", None)
    request.META["SERVER_NAME"] = "fallback.example.com"
    request.META["SERVER_PORT"] = port
    request.META["wsgi.url_scheme"] = scheme

    assert EventMiddleware.get_host(request) == expected


@pytest.mark.parametrize("path", ("/robots.txt", "/redirect/", "/api/events/"))
@override_settings(SITE_NETLOC="testserver")
def test_call_allows_any_domain_for_special_paths(path):
    request = _domain_request(path, "random.example.com", user=AnonymousUser())

    response = _make_middleware()(request)

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path_template", "event_attached"),
    (
        ("/{slug}/does-not-exist", True),
        ("/orga/event/{slug}/nonsense", True),
        ("/no-such-event/sub/path", False),
    ),
    ids=("event-subpath", "orga-event-subpath", "unknown-path"),
)
@override_settings(SITE_NETLOC="testserver")
def test_call_attaches_event_on_unresolved_path(path_template, event_attached):
    event = EventFactory()
    request = _domain_request(path_template.format(slug=event.slug), "testserver")

    with pytest.raises(Resolver404):
        _make_middleware()(request)

    assert getattr(request, "event", None) == (event if event_attached else None)


def test_attach_event_from_path_noop_on_empty_path():
    request = rf.get("/")

    EventMiddleware._attach_event_from_path(request)

    assert not hasattr(request, "event")


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_call_event_custom_domain_match_sets_flag():
    event = EventFactory(custom_domain="https://custom.example.com")
    request = _domain_request(
        f"/{event.slug}/", "custom.example.com", user=AnonymousUser()
    )

    response = _make_middleware()(request)

    assert response.status_code == 200
    assert request.event == event
    assert request.uses_custom_domain is True


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver")
def test_call_orga_url_stays_on_default_domain_with_custom_domain():
    event = EventFactory(custom_domain="https://custom.example.com")
    request = _domain_request(
        f"/orga/event/{event.slug}/", "testserver", user=UserFactory()
    )

    response = _make_middleware()(request)

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "custom_domain",
    (None, "https://custom.example.com"),
    ids=("no-custom-domain", "other-custom-domain"),
)
@override_settings(SITE_NETLOC="testserver")
def test_call_orga_url_on_wrong_domain_redirects_to_main_domain(custom_domain):
    event = EventFactory(custom_domain=custom_domain)
    request = _domain_request(
        f"/orga/event/{event.slug}/", "wrong.example.com", user=UserFactory()
    )

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url.startswith(settings.SITE_URL)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "custom_domain",
    (None, "https://custom.example.com"),
    ids=("no-custom-domain", "other-custom-domain"),
)
@override_settings(SITE_NETLOC="testserver")
def test_call_event_on_wrong_domain_raises_404(custom_domain):
    event = EventFactory(custom_domain=custom_domain)
    request = _domain_request(
        f"/{event.slug}/", "wrong.example.com", user=AnonymousUser()
    )

    with pytest.raises(Http404):
        _make_middleware()(request)


@override_settings(SITE_NETLOC="testserver.com", DEBUG=True)
def test_call_debug_mode_allows_any_domain():
    request = _domain_request("/400", "anything.example.com", user=AnonymousUser())

    response = _make_middleware()(request)

    assert response.status_code == 200


@pytest.mark.parametrize("host", ("localhost", "127.0.0.1", "testserver"))
@override_settings(SITE_NETLOC="production.example.com", DEBUG=False)
def test_call_local_hosts_always_allowed(host):
    request = _domain_request("/400", host, user=AnonymousUser())

    response = _make_middleware()(request)

    assert response.status_code == 200


@override_settings(
    SITE_NETLOC="testserver.com", SITE_URL="https://testserver.com", DEBUG=False
)
def test_call_orga_on_unknown_domain_redirects_to_site_url():
    request = _domain_request("/orga/login/", "unknown.example.com")

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == "https://testserver.com/orga/login/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_call_custom_domain_redirects_to_public_event():
    event = EventFactory(custom_domain="http://custom.example.com", is_public=True)
    request = _domain_request("/400", "custom.example.com")

    response = _make_middleware()(request)

    assert response.status_code == 302
    assert response.url == f"http://custom.example.com/{event.slug}/"


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_call_custom_domain_without_public_event_shows_start_page():
    event = EventFactory(custom_domain="http://custom.example.com", is_public=False)
    request = _domain_request("/400", "custom.example.com", user=AnonymousUser())

    response = _make_middleware()(request)

    assert response.status_code == 200
    assert request.uses_custom_domain is True
    # The middleware stashes the matching events on the request so the
    # GeneralView can reuse them without re-running the same query.
    assert list(request.custom_domain_events) == [event]


@pytest.mark.django_db
@override_settings(SITE_NETLOC="testserver.com", DEBUG=False)
def test_call_unknown_domain_raises_disallowed_host():
    request = _domain_request("/400", "unknown.example.com")

    with pytest.raises(DisallowedHost):
        _make_middleware()(request)


@pytest.mark.django_db
def test_update_csp_adds_csp_for_orga_with_custom_domain():
    event = EventFactory(custom_domain="https://custom.example.com")
    request = rf.get(f"/orga/event/{event.slug}/")
    request.event = event
    response = HttpResponse()

    result = _make_middleware()._update_csp(request, response)

    assert result._csp_update["form-action"] == [event.urls.base.full()]


def test_update_csp_no_csp_without_event():
    request = rf.get("/orga/login/")
    request.event = None
    response = HttpResponse()

    result = _make_middleware()._update_csp(request, response)

    assert not hasattr(result, "_csp_update")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("custom_domain", "path_template"),
    ((None, "/orga/event/{slug}/"), ("https://custom.example.com", "/{slug}/")),
    ids=("no-custom-domain", "non-orga-path"),
)
def test_update_csp_no_csp(custom_domain, path_template):
    event = EventFactory(custom_domain=custom_domain)
    request = rf.get(path_template.format(slug=event.slug))
    request.event = event
    response = HttpResponse()

    result = _make_middleware()._update_csp(request, response)

    assert not hasattr(result, "_csp_update")
