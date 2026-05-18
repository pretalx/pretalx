# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponse
from django.test import RequestFactory
from django.utils import translation

from pretalx.common.middleware.event import EventPermissionMiddleware
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

    return EventPermissionMiddleware(get_response)


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


@pytest.mark.parametrize(
    "url_name", EventPermissionMiddleware.UNAUTHENTICATED_ORGA_URLS
)
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


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param("en", "en", id="valid"),
        pytest.param("en-us", "en", id="variant_resolution"),
        pytest.param("fr", None, id="unsupported"),
        pytest.param(None, None, id="none"),
        pytest.param("", None, id="empty"),
        pytest.param("zzz-zz-zz", None, id="nonsense"),
    ),
)
def test_validate_language(value, expected):
    result = EventPermissionMiddleware._validate_language(value, ["en", "de"])

    assert result == expected


@pytest.mark.parametrize(
    ("query_params", "expected"),
    (
        pytest.param({"lang": "de"}, "de", id="valid_lang"),
        pytest.param({"lang": "xx"}, None, id="unsupported_lang"),
        pytest.param({}, None, id="no_param"),
    ),
)
def test_language_from_request(query_params, expected):
    middleware = _make_middleware()
    request = rf.get("/", query_params)
    request.COOKIES = {}

    result = middleware._language_from_request(request, ["en", "de"])

    assert result == expected


def test_language_from_request_sets_cookie_on_valid_lang():
    middleware = _make_middleware()
    request = rf.get("/", {"lang": "de"})
    request.COOKIES = {}

    middleware._language_from_request(request, ["en", "de"])

    assert request.COOKIES[settings.LANGUAGE_COOKIE_NAME] == "de"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale", "expected"),
    (
        pytest.param("de", "de", id="supported"),
        pytest.param("fr", None, id="unsupported"),
    ),
)
def test_language_from_user_authenticated(locale, expected):
    middleware = _make_middleware()
    user = UserFactory(locale=locale)
    request = rf.get("/")
    request.user = user

    result = middleware._language_from_user(request, ["en", "de"])

    assert result == expected


def test_language_from_user_anonymous():
    middleware = _make_middleware()
    request = rf.get("/")
    request.user = AnonymousUser()

    result = middleware._language_from_user(request, ["en", "de"])

    assert result is None


@pytest.mark.parametrize(
    ("cookie_value", "expected"),
    (pytest.param("de", "de", id="valid"), pytest.param("xx", None, id="invalid")),
)
def test_language_from_cookie(cookie_value, expected):
    middleware = _make_middleware()
    request = rf.get("/")
    request.COOKIES = {settings.LANGUAGE_COOKIE_NAME: cookie_value}

    result = middleware._language_from_cookie(request, ["en", "de"])

    assert result == expected


def test_language_from_cookie_missing():
    middleware = _make_middleware()
    request = rf.get("/")
    request.COOKIES = {}

    result = middleware._language_from_cookie(request, ["en", "de"])

    assert result is None


@pytest.mark.parametrize(
    ("accept_header", "expected"),
    (
        pytest.param("de,en;q=0.5", "de", id="first_choice"),
        pytest.param("fr,de;q=0.8,en;q=0.5", "de", id="second_choice"),
        pytest.param("fr,es;q=0.5", None, id="no_match"),
        pytest.param("*,de;q=0.5", None, id="wildcard_stops_search"),
        pytest.param("", None, id="no_header"),
    ),
)
def test_language_from_browser(accept_header, expected):
    middleware = _make_middleware()
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE=accept_header)

    result = middleware._language_from_browser(request, ["en", "de"])

    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale", "expected"),
    (
        pytest.param("de", "de", id="supported"),
        pytest.param("fr", None, id="unsupported"),
    ),
)
def test_language_from_event_with_event(locale, expected):
    middleware = _make_middleware()
    event = EventFactory(locale=locale)
    request = rf.get("/")
    request.event = event

    result = middleware._language_from_event(request, ["en", "de"])

    assert result == expected


def test_language_from_event_without_event():
    middleware = _make_middleware()
    request = rf.get("/")

    result = middleware._language_from_event(request, ["en", "de"])

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
    request.user = user
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.timezone == "Europe/Berlin"


def test_select_locale_sets_timezone_from_settings_for_anonymous_without_event():
    middleware = _make_middleware()
    request = rf.get("/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.timezone == settings.TIME_ZONE


@pytest.mark.django_db
def test_select_locale_query_param_takes_priority():
    middleware = _make_middleware()
    event = EventFactory(locale_array="en,de")
    request = rf.get("/", {"lang": "de"})
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == "de"


@pytest.mark.django_db
def test_select_locale_user_locale_over_cookie():
    middleware = _make_middleware()
    event = EventFactory(locale_array="en,de")
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
    event = EventFactory(locale_array="en,de")
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE="en;q=1.0")
    request.event = event
    request.user = AnonymousUser()
    request.COOKIES = {settings.LANGUAGE_COOKIE_NAME: "de"}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == "de"


def test_select_locale_falls_back_to_settings_language_code():
    middleware = _make_middleware()
    request = rf.get("/")
    request.user = AnonymousUser()
    request.COOKIES = {}

    middleware._select_locale(request)

    assert request.LANGUAGE_CODE == settings.LANGUAGE_CODE


@pytest.mark.django_db
def test_call_sets_event_on_request(event):
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    middleware(request)

    assert request.event == event


def _cfp_request(event, user):
    request = rf.get(f"/{event.slug}/")
    request.user = user
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}
    return request


@pytest.mark.django_db
def test_call_annotates_has_cfp_submissions_for_speaker():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    SpeakerRoleFactory(submission=SubmissionFactory(event=event), speaker=speaker)

    request = _cfp_request(event, speaker.user)
    _make_middleware()(request)

    assert request.event.has_cfp_submissions is True


@pytest.mark.django_db
def test_call_annotates_has_cfp_submissions_counts_drafts():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    SpeakerRoleFactory(
        submission=SubmissionFactory(event=event, state=SubmissionStates.DRAFT),
        speaker=speaker,
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
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}
    _make_middleware()(request)

    assert not hasattr(request.event, "has_cfp_submissions")


@pytest.mark.django_db
def test_call_sets_organiser_on_request(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/organiser/{event.organiser.slug}/")
    request.user = UserFactory()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    middleware(request)

    assert request.organiser == event.organiser


@pytest.mark.django_db
def test_call_unknown_event_raises_404():
    middleware = _make_middleware()
    request = rf.get("/nonexistent-event-slug/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    with pytest.raises(Http404):
        middleware(request)


@pytest.mark.django_db
def test_call_event_with_custom_domain_redirects_from_main_domain():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert response.url == f"https://custom.example.com/{event.slug}/"
    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_call_orga_url_on_custom_domain_redirects_to_site_url(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.user = UserFactory()
    request.uses_custom_domain = True
    request.host = "custom.example.com"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert response.url.startswith(settings.SITE_URL)


@pytest.mark.django_db
def test_call_orga_url_anonymous_redirects_to_login(event):
    middleware = _make_middleware()
    request = rf.get(f"/orga/event/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_call_api_path_is_exempt_from_custom_domain_redirect():
    event = EventFactory(custom_domain="https://custom.example.com")
    middleware = _make_middleware()
    request = rf.get(f"/api/events/{event.slug}/submissions/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_call_api_exempt_response_gets_cors_header(event):
    middleware = _make_middleware()
    request = rf.get(f"/api/events/{event.slug}/submissions/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_call_sets_language_code_on_request(event):
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    middleware(request)

    assert request.LANGUAGE_CODE in event.locales


@pytest.mark.django_db
def test_call_without_event_passes_through():
    middleware = _make_middleware()
    request = rf.get("/orga/login/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_call_event_without_custom_domain_no_redirect(event):
    assert event.custom_domain is None
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_call_activates_translation(event):
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    middleware(request)

    assert translation.get_language() in event.locales


@pytest.mark.django_db
def test_call_disabled_plugin_raises_404(event):
    assert "tests.dummy_app" not in event.plugin_list
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/test-plugin/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    with pytest.raises(Http404):
        middleware(request)


@pytest.mark.django_db
def test_call_enabled_plugin_passes_through():
    event = EventFactory(plugins="dummy_app")
    middleware = _make_middleware()
    request = rf.get(f"/{event.slug}/test-plugin/")
    request.user = AnonymousUser()
    request.uses_custom_domain = False
    request.host = "testserver"
    request.port = None
    request.COOKIES = {}

    response = middleware(request)

    assert response.status_code == 200
