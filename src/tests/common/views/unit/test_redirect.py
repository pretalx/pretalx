# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import urllib.parse

import pytest
from django.core import signing
from django.test import RequestFactory

from pretalx.common.views.redirect import (
    _is_samesite_referer,
    build_login_redirect_url,
    get_login_redirect,
    get_next_url,
    safelink,
)
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

rf = RequestFactory()


@pytest.mark.parametrize(
    ("referer", "expected"),
    (
        ("http://testserver/some/page/", True),
        (None, False),
        ("http://evil.example.com/page/", False),
        ("//testserver/page/", False),
        ("https://testserver/page/", False),
    ),
    ids=[
        "same_origin",
        "no_header",
        "different_host",
        "empty_scheme",
        "different_scheme",
    ],
)
def test_is_samesite_referer(event, referer, expected):
    kwargs = {"headers": {"referer": referer}} if referer is not None else {}
    request = make_request(event, **kwargs)

    assert _is_samesite_referer(request) is expected


def test_safelink_produces_signed_url():
    url = "https://example.com"

    result = safelink(url)

    assert result.startswith("/redirect/?url=")
    signer = signing.Signer(salt="safe-redirect")
    encoded_signed = result.split("?url=")[1]
    signed = urllib.parse.unquote(encoded_signed)
    assert signer.unsign(signed) == url


@pytest.mark.parametrize(
    ("query_string", "omit_params", "expected"),
    (
        ("", None, None),
        ("next=/dashboard/", None, "/dashboard/"),
        ("next=http://evil.com/", None, None),
    ),
    ids=("no_next_param", "valid_next", "rejects_external_url"),
)
def test_get_next_url(query_string, omit_params, expected):
    request = rf.get("/", QUERY_STRING=query_string)
    assert get_next_url(request, omit_params=omit_params) == expected


def test_get_next_url_preserves_extra_params():
    request = rf.get("/", QUERY_STRING="next=/dashboard/&page=2&sort=name")
    result = get_next_url(request)
    assert result.startswith("/dashboard/?")
    assert "page=2" in result
    assert "sort=name" in result


def test_get_next_url_omits_specified_params():
    request = rf.get("/", QUERY_STRING="next=/dashboard/&page=2&secret=yes")
    result = get_next_url(request, omit_params=["secret"])
    assert "secret" not in result
    assert "page=2" in result


def test_get_next_url_returns_plain_url_when_no_extra_params():
    request = rf.get("/", QUERY_STRING="next=/dashboard/")
    result = get_next_url(request)
    assert result == "/dashboard/"
    assert "?" not in result


def test_get_login_redirect_with_event_on_orga_path(event):
    request = rf.get(f"/orga/event/{event.slug}/")
    request.event = event

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert response.url.startswith(event.orga_urls.login.full())
    assert f"next=/orga/event/{event.slug}/" in response.url


def test_get_login_redirect_with_event_on_cfp_path(event):
    request = rf.get(f"/{event.slug}/cfp")
    request.event = event

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert response.url.startswith(event.urls.login.full())
    assert f"next=/{event.slug}/cfp" in response.url


def test_get_login_redirect_without_event():
    request = rf.get("/orga/")

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert response.url.startswith("/orga/login/")
    assert "next=/orga/" in response.url


def test_get_login_redirect_preserves_query_params():
    request = rf.get("/orga/", {"foo": "bar"})

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert "foo=bar" in response.url


def test_get_login_redirect_uses_explicit_next_param():
    request = rf.get("/orga/", {"next": "/some/path/"})

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert "next=/some/path/" in response.url


@pytest.mark.parametrize(
    ("return_path", "fragment", "orga", "expected_next"),
    (
        ("/talk/CODE/", None, False, "/talk/CODE/"),
        ("/talk/CODE/", "signup", False, "/talk/CODE/%23signup"),
        ("/talk/CODE/", "signup-success", False, "/talk/CODE/%23signup-success"),
        ("/talk/CODE/?x=1", "signup", False, "/talk/CODE/%3Fx%3D1%23signup"),
        ("/orga/", None, True, "/orga/"),
    ),
    ids=("no_fragment", "simple", "hyphenated", "with_query", "orga_login"),
)
def test_build_login_redirect_url(event, return_path, fragment, orga, expected_next):
    url = build_login_redirect_url(event, return_path, fragment=fragment, orga=orga)

    login_url = event.orga_urls.login if orga else event.urls.login
    assert url == f"{login_url}?next={expected_next}"
