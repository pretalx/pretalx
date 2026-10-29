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
        ("next=/dashboard/&page=2&sort=name", None, "/dashboard/?page=2&sort=name"),
        ("next=/dashboard/&page=2&secret=yes", ["secret"], "/dashboard/?page=2"),
    ),
    ids=(
        "no_next_param",
        "valid_next",
        "rejects_external_url",
        "preserves_extra_params",
        "omits_specified_params",
    ),
)
def test_get_next_url(query_string, omit_params, expected):
    request = rf.get("/", QUERY_STRING=query_string)
    assert get_next_url(request, omit_params=omit_params) == expected


@pytest.mark.parametrize(
    ("path", "query", "with_event", "expected"),
    (
        ("/orga/event/{slug}/", {}, True, "{orga_login}?next=/orga/event/{slug}/"),
        ("/{slug}/cfp", {}, True, "{login}?next=/{slug}/cfp"),
        ("/orga/", {}, False, "/orga/login/?next=/orga/"),
        ("/orga/", {"foo": "bar"}, False, "/orga/login/?next=/orga/&foo=bar"),
        ("/orga/", {"next": "/some/path/"}, False, "/orga/login/?next=/some/path/"),
    ),
    ids=("orga_path", "cfp_path", "without_event", "preserves_query", "explicit_next"),
)
def test_get_login_redirect(event, path, query, with_event, expected):
    request = rf.get(path.format(slug=event.slug), query)
    request.event = event if with_event else None

    response = get_login_redirect(request)

    assert response.status_code == 302
    assert response.url == expected.format(
        slug=event.slug,
        orga_login=event.orga_urls.login.full(),
        login=event.urls.login.full(),
    )


def test_get_login_redirect_uses_hx_redirect_header_for_htmx_requests(event):
    request = rf.get(f"/orga/event/{event.slug}/", headers={"hx-request": "true"})
    request.event = event

    response = get_login_redirect(request)

    assert response.status_code == 286
    assert response.has_header("Location") is False
    assert response["HX-Redirect"].startswith(event.orga_urls.login.full())
    assert f"next=/orga/event/{event.slug}/" in response["HX-Redirect"]


def test_get_login_redirect_sends_htmx_back_to_the_page_not_the_fragment(event):
    request = rf.get(
        f"/orga/event/{event.slug}/mails/sidebar-count",
        {"format": "badge"},
        headers={
            "hx-request": "true",
            "hx-current-url": f"http://testserver/orga/event/{event.slug}/mails/?page=2",
        },
    )
    request.event = event

    response = get_login_redirect(request)

    assert response.status_code == 286
    assert response["HX-Redirect"] == (
        f"{event.orga_urls.login.full()}?next="
        f"/orga/event/{event.slug}/mails/%3Fpage%3D2"
    )


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
