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
    ("query_params", "supported", "expected"),
    (
        pytest.param({"lang": "de"}, ["en", "de"], "de", id="valid_lang"),
        pytest.param(
            {"lang": "de-formal"}, ["en", "de"], "de", id="unsupported_variant"
        ),
        pytest.param({"lang": "pt-br"}, ["en", "pt-pt"], "pt-pt", id="sibling_variant"),
        pytest.param(
            {"lang": "zh-hant"}, ["en", "zh-hans"], "zh-hans", id="sibling_script"
        ),
        pytest.param(
            {"lang": "zh-Hans"},
            ["en", "zh-hant", "zh-hans"],
            "zh-hans",
            id="exact_variant_mixed_case",
        ),
        pytest.param(
            {"lang": "zh-TW"},
            ["en", "zh-hans", "zh-hant"],
            "zh-hant",
            id="region_fallback_traditional",
        ),
        pytest.param(
            {"lang": "zh-cn"},
            ["en", "zh-hant", "zh-hans"],
            "zh-hans",
            id="region_fallback_simplified",
        ),
        pytest.param(
            {"lang": "de-DE"}, ["en", "de-formal", "de"], "de", id="region_base"
        ),
        pytest.param({"lang": "xx"}, ["en", "de"], None, id="unsupported_lang"),
        pytest.param({}, ["en", "de"], None, id="no_param"),
    ),
)
def test_language_from_query(query_params, supported, expected):
    request = rf.get("/", query_params)
    request.COOKIES = {}

    result = get_language_from_query(request, supported)

    assert result == expected
    assert request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("make_user", "expected"),
    (
        pytest.param(lambda: UserFactory(locale="de"), "de", id="supported"),
        pytest.param(lambda: UserFactory(locale="fr"), None, id="unsupported"),
        pytest.param(AnonymousUser, None, id="anonymous"),
    ),
)
def test_language_from_user(make_user, expected):
    request = rf.get("/")
    request.user = make_user()

    result = get_language_from_user(request, ["en", "de"])

    assert result == expected


@pytest.mark.parametrize(
    ("cookies", "expected"),
    (
        pytest.param({settings.LANGUAGE_COOKIE_NAME: "de"}, "de", id="valid"),
        pytest.param({settings.LANGUAGE_COOKIE_NAME: "xx"}, None, id="invalid"),
        pytest.param({}, None, id="missing"),
    ),
)
def test_language_from_cookie(cookies, expected):
    request = rf.get("/")
    request.COOKIES = cookies

    result = get_language_from_cookie(request, ["en", "de"])

    assert result == expected


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
    ("query", "accept_header", "cookies", "expected"),
    (
        pytest.param(
            {},
            "en;q=1.0",
            {settings.LANGUAGE_COOKIE_NAME: "de"},
            "de",
            id="cookie_over_browser",
        ),
        pytest.param(
            {},
            "xx;q=1.0,de;q=0.8",
            {settings.LANGUAGE_COOKIE_NAME: "xx"},
            "de",
            id="browser_when_cookie_unsupported",
        ),
        pytest.param({}, "sw", {}, settings.LANGUAGE_CODE, id="default_when_no_match"),
        pytest.param(
            {"lang": "de"}, "", {}, settings.LANGUAGE_CODE, id="ignores_query"
        ),
    ),
)
def test_language_from_early_request(query, accept_header, cookies, expected):
    request = rf.get("/", query, HTTP_ACCEPT_LANGUAGE=accept_header)
    request.COOKIES = cookies

    assert get_language_from_early_request(request) == expected


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
    assert response.headers["Vary"] == "Accept-Language"


def test_middleware_deactivates_stale_timezone():
    timezone.activate(zoneinfo.ZoneInfo("Europe/Berlin"))
    request = rf.get("/")

    _make_middleware()(request)

    assert timezone.get_current_timezone_name() == settings.TIME_ZONE


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
