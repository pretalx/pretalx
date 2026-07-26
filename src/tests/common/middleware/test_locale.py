# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import zoneinfo

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers

from pretalx.common.middleware.locale import (
    LocaleMiddleware,
    get_language_from_browser,
    get_language_from_cookie,
    get_language_from_early_request,
    get_language_from_event,
    get_language_from_query,
    get_language_from_user,
    validate_language,
)
from tests.factories import EventFactory, UserFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


def _make_middleware(get_response=None):
    def default_get_response(request):
        return HttpResponse("ok")

    return LocaleMiddleware(get_response or default_get_response)


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
    result = validate_language(value, ["en", "de"])

    assert result == expected


@pytest.mark.parametrize(
    ("query_params", "expected"),
    (
        pytest.param({"lang": "de"}, "de", id="valid_lang"),
        pytest.param({"lang": "xx"}, None, id="unsupported_lang"),
        pytest.param({}, None, id="no_param"),
    ),
)
def test_language_from_query(query_params, expected):
    request = rf.get("/", query_params)
    request.COOKIES = {}

    result = get_language_from_query(request, ["en", "de"])

    assert result == expected


def test_language_from_query_sets_cookie_on_valid_lang():
    request = rf.get("/", {"lang": "de"})
    request.COOKIES = {}

    get_language_from_query(request, ["en", "de"])

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
    user = UserFactory(locale=locale)
    request = rf.get("/")
    request.user = user

    result = get_language_from_user(request, ["en", "de"])

    assert result == expected


def test_language_from_user_anonymous():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = get_language_from_user(request, ["en", "de"])

    assert result is None


@pytest.mark.parametrize(
    ("cookie_value", "expected"),
    (pytest.param("de", "de", id="valid"), pytest.param("xx", None, id="invalid")),
)
def test_language_from_cookie(cookie_value, expected):
    request = rf.get("/")
    request.COOKIES = {settings.LANGUAGE_COOKIE_NAME: cookie_value}

    result = get_language_from_cookie(request, ["en", "de"])

    assert result == expected


def test_language_from_cookie_missing():
    request = rf.get("/")
    request.COOKIES = {}

    result = get_language_from_cookie(request, ["en", "de"])

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
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE=accept_header)

    result = get_language_from_browser(request, ["en", "de"])

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
    event = EventFactory(locale=locale)
    request = rf.get("/")
    request.event = event

    result = get_language_from_event(request, ["en", "de"])

    assert result == expected


def test_language_from_event_without_event():
    request = rf.get("/")

    result = get_language_from_event(request, ["en", "de"])

    assert result is None


@pytest.mark.parametrize(
    ("accept_header", "cookies", "expected"),
    (
        pytest.param(
            "en;q=1.0",
            {settings.LANGUAGE_COOKIE_NAME: "de"},
            "de",
            id="cookie_over_browser",
        ),
        pytest.param(
            "xx;q=1.0,de;q=0.8",
            {settings.LANGUAGE_COOKIE_NAME: "xx"},
            "de",
            id="browser_when_cookie_unsupported",
        ),
        pytest.param("sw", {}, settings.LANGUAGE_CODE, id="default_when_no_match"),
    ),
)
def test_language_from_early_request(accept_header, cookies, expected):
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE=accept_header)
    request.COOKIES = cookies

    assert get_language_from_early_request(request) == expected


def test_language_from_early_request_ignores_query_parameter():
    request = rf.get("/", {"lang": "de"})
    request.COOKIES = {}

    assert get_language_from_early_request(request) == settings.LANGUAGE_CODE


@pytest.mark.parametrize(
    ("stale_language", "accept_header", "expected"),
    (
        pytest.param("en", "de", "de", id="browser_language"),
        pytest.param("de", "sw", settings.LANGUAGE_CODE, id="default_language"),
    ),
)
def test_middleware_activates_language_without_user_or_event(
    stale_language, accept_header, expected
):
    translation.activate(stale_language)
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE=accept_header)

    response = _make_middleware()(request)

    assert response.content == b"ok"
    assert expected == request.LANGUAGE_CODE
    assert translation.get_language() == expected


def test_middleware_deactivates_stale_timezone():
    timezone.activate(zoneinfo.ZoneInfo("Europe/Berlin"))
    request = rf.get("/")

    _make_middleware()(request)

    assert timezone.get_current_timezone_name() == settings.TIME_ZONE


def test_middleware_marks_response_as_varying_by_language():
    request = rf.get("/", HTTP_ACCEPT_LANGUAGE="de")

    response = _make_middleware()(request)

    assert response.headers["Vary"] == "Accept-Language"


def test_middleware_keeps_other_vary_headers():
    def get_response(request):
        response = HttpResponse("ok")
        patch_vary_headers(response, ("Cookie",))
        return response

    request = rf.get("/")

    response = _make_middleware(get_response)(request)

    assert response.headers["Vary"] == "Cookie, Accept-Language"


def test_middleware_sets_content_language_from_active_language():
    def get_response(request):
        translation.activate("de")
        return HttpResponse("ok")

    request = rf.get("/", HTTP_ACCEPT_LANGUAGE="en")

    response = _make_middleware(get_response)(request)

    assert request.LANGUAGE_CODE == "en"
    assert response.headers["Content-Language"] == "de"


def test_middleware_keeps_explicit_content_language():
    def get_response(request):
        response = HttpResponse("ok")
        response["Content-Language"] = "de"
        return response

    request = rf.get("/", HTTP_ACCEPT_LANGUAGE="en")

    response = _make_middleware(get_response)(request)

    assert response.headers["Content-Language"] == "de"
