# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import BadRequest
from django.http import HttpResponse
from django.test import RequestFactory

from pretalx.common.middleware.security import RejectInvalidInputMiddleware

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
