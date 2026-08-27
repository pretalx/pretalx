# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
import time

import pytest
from django.core.exceptions import BadRequest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from pretalx.common.middleware.security import (
    RejectInvalidInputMiddleware,
    SessionValidityMiddleware,
)
from tests.factories import UserFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

rf = RequestFactory()


def dummy_response(request):
    return HttpResponse("ok")


middleware = RejectInvalidInputMiddleware(dummy_response)


def test_clean_request_passes():
    request = rf.get("/?foo=bar&baz=quux")
    assert middleware.process_request(request) is None


def test_clean_request_reaches_response():
    request = rf.get("/?foo=bar&baz=quux")
    response = middleware(request)
    assert response.status_code == 200
    assert response.content == b"ok"


def test_nullbyte_in_path_rejected():
    request = rf.get("/api/events/foo\x00bar/")
    assert "\x00" in request.path
    with pytest.raises(BadRequest):
        middleware.process_request(request)


@pytest.mark.parametrize(
    "query_string",
    (
        "foo=ba\x00r",  # raw nullbyte
        "foo=ba%00r",  # percent-encoded nullbyte
    ),
)
def test_nullbyte_in_query_string_rejected(query_string):
    request = rf.get("/")
    request.META["QUERY_STRING"] = query_string
    with pytest.raises(BadRequest):
        middleware.process_request(request)


@pytest.mark.parametrize(
    "data",
    (
        "foo=ba\x00r",  # nullbyte in value
        "ba\x00r=foo",  # nullbyte in key
    ),
)
def test_nullbyte_in_urlencoded_post_rejected(data):
    request = rf.post("/", data=data, content_type="application/x-www-form-urlencoded")
    with pytest.raises(BadRequest):
        middleware.process_request(request)


def test_clean_urlencoded_post_passes():
    request = rf.post(
        "/", data="foo=bar", content_type="application/x-www-form-urlencoded"
    )
    assert middleware.process_request(request) is None


def test_multipart_body_is_not_inspected():
    # Multipart bodies are deliberately not scanned: file uploads may
    # legitimately contain nullbytes, and accessing request.POST for them in
    # middleware would consume the upload stream.
    request = rf.post("/", data={"foo": "ba\x00r"})
    assert request.content_type == "multipart/form-data"
    assert middleware.process_request(request) is None


session_middleware = SessionValidityMiddleware(dummy_response)


def _orga_request(user, path="/orga/event/", headers=None, **session):
    # EventMiddleware classifies the URL and stashes the answer; this gate only
    # reads it.
    request = make_request(
        None, user=user, path=path, headers=headers, is_orga_url=True
    )
    request.session.update(session)
    return request


def _idle_session():
    return {
        "pretalx_auth_login_time": int(time.time()) - 200,
        "pretalx_auth_last_used": int(time.time()) - 200,
    }


def test_session_validity_lets_fresh_orga_session_through():
    request = _orga_request(
        UserFactory(),
        pretalx_auth_login_time=int(time.time()),
        pretalx_auth_last_used=int(time.time()),
    )

    assert session_middleware(request).status_code == 200


def test_session_validity_ignores_anonymous_users():
    request = make_request(None, path="/orga/event/", is_orga_url=True)

    assert session_middleware(request).status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_ignores_public_pages():
    request = make_request(
        None, user=UserFactory(), path="/democon/schedule/", is_orga_url=False
    )
    request.session.update(_idle_session())

    assert session_middleware(request).status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
@pytest.mark.parametrize(
    "path", ("/orga/login/", "/orga/reauth/"), ids=("login", "reauth")
)
def test_session_validity_lets_idle_session_through_on_exempt_paths(path):
    request = _orga_request(UserFactory(), path=path, **_idle_session())

    assert session_middleware(request).status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_redirects_idle_session_to_reauth():
    request = _orga_request(UserFactory(), **_idle_session())

    response = session_middleware(request)

    assert response.status_code == 302
    assert response.url == "/orga/reauth/?next=/orga/event/"


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_hands_htmx_the_redirect_as_a_header():
    request = _orga_request(
        UserFactory(), headers={"HX-Request": "true"}, **_idle_session()
    )

    response = session_middleware(request)

    assert response.status_code == 286
    assert response["HX-Redirect"] == "/orga/reauth/?next=/orga/event/"


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_sends_htmx_back_to_the_page_not_the_fragment():
    request = _orga_request(
        UserFactory(),
        path="/orga/event/democon/mails/sidebar-count",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://testserver/orga/event/democon/mails/?page=2",
        },
        **_idle_session(),
    )

    response = session_middleware(request)

    assert response.status_code == 286
    assert response["HX-Redirect"] == (
        "/orga/reauth/?next=/orga/event/democon/mails/%3Fpage%3D2"
    )


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_falls_back_to_own_path_for_unusable_htmx_url():
    request = _orga_request(
        UserFactory(),
        path="/orga/event/democon/mails/sidebar-count",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "https://evil.example.org/orga/",
        },
        **_idle_session(),
    )

    response = session_middleware(request)

    assert response.status_code == 286
    assert response["HX-Redirect"] == (
        "/orga/reauth/?next=/orga/event/democon/mails/sidebar-count"
    )


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_session_validity_answers_background_requests_with_a_login_url():
    request = _orga_request(
        UserFactory(), headers={"X-Requested-With": "XMLHttpRequest"}, **_idle_session()
    )

    response = session_middleware(request)

    assert response.status_code == 401
    assert response["X-Login-Url"] == "/orga/reauth/"
    assert json.loads(response.content) == {"detail": "Authentication required"}
