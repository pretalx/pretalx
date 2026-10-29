# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.cache import caches
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.cache import learn_cache_key

from pretalx.common.views.cache import (
    conditional_cache_page,
    etag_cache_page,
    get_etag,
    get_requested_etag,
    patched_response,
    should_cache,
)
from tests.utils import make_request

pytestmark = [pytest.mark.unit]


@pytest.mark.django_db
def test_get_requested_etag(event):
    assert (
        get_requested_etag(make_request(event, headers={"If-None-Match": '"abc123"'}))
        == "abc123"
    )
    assert get_requested_etag(make_request(event)) is None


def test_get_etag_hashes_content():
    assert get_etag(HttpResponse(b"identical")) == get_etag(HttpResponse(b"identical"))
    assert get_etag(HttpResponse(b"content-a")) != get_etag(HttpResponse(b"content-b"))
    assert len(get_etag(HttpResponse(b"hello world"))) == 32
    assert len(get_etag(HttpResponse("text content"))) == 32


@pytest.mark.parametrize(
    ("response_factory", "expected"),
    (
        (lambda: HttpResponse("ok"), True),
        (lambda: HttpResponse(status=304), True),
        (lambda: StreamingHttpResponse(iter(["chunk"])), False),
        (lambda: HttpResponse("not found", status=404), False),
    ),
    ids=("200_ok", "304_not_modified", "streaming", "404_error"),
)
@pytest.mark.django_db
def test_should_cache(event, response_factory, expected):
    request = make_request(event)

    assert should_cache(request, response_factory()) is expected


@pytest.mark.django_db
def test_should_cache_false_for_private_responses(event):
    request = make_request(event)
    private = HttpResponse("ok")
    private["Cache-Control"] = "private"
    with_cookie = HttpResponse("ok")
    with_cookie.set_cookie("session", "abc")
    with_cookie["Vary"] = "Cookie"

    assert should_cache(request, private) is False
    assert should_cache(request, with_cookie) is False


def test_patched_response_sets_cache_and_custom_headers():
    response = HttpResponse("ok")

    result = patched_response(response, 300, headers={"X-Custom": "value"})

    assert result["Cache-Control"] == "max-age=300"
    assert result["X-Custom"] == "value"


@pytest.mark.django_db
def test_conditional_cache_page_caches_only_matching_get_requests(event):
    calls = []

    @conditional_cache_page(300)
    def view(request):
        calls.append("plain")
        return HttpResponse("ok")

    @conditional_cache_page(300, condition=lambda req: False)
    def conditional_view(request):
        calls.append("conditional")
        return HttpResponse("ok")

    post_request = make_request(event, method="post", path="/test/")
    get_request = make_request(event, path="/cache-get/")

    view(post_request)
    view(post_request)
    conditional_view(get_request)
    conditional_view(get_request)
    assert view(get_request).status_code == 200
    assert view(get_request).status_code == 200

    assert calls == ["plain", "plain", "conditional", "conditional", "plain"]


@pytest.mark.django_db
@pytest.mark.parametrize("server_timeout", (None, 120))
def test_etag_cache_page_serves_cached_response_by_etag(event, server_timeout):
    calls = []

    def handler(request):
        calls.append(1)
        return HttpResponse("cached content")

    def cached(request):
        return etag_cache_page(
            60,
            server_timeout=server_timeout,
            request=request,
            request_args=(),
            request_kwargs={},
            handler=handler,
        )

    first = cached(make_request(event, path="/cacheable/"))
    etag_value = first["ETag"].strip('"')

    assert first.status_code == 200
    assert cached(make_request(event, path="/cacheable/")).status_code == 200
    assert calls == [1]

    matching = make_request(
        event, path="/cacheable/", headers={"If-None-Match": f'"{etag_value}"'}
    )
    assert cached(matching).status_code == 304

    stale = make_request(
        event, path="/cacheable/", headers={"If-None-Match": '"stale-etag-value"'}
    )
    assert cached(stale).status_code == 200
    assert calls == [1]


@pytest.mark.django_db
def test_etag_cache_page_callable_key_prefix_and_custom_headers(event):
    prefix_calls = []

    def handler(request):
        return HttpResponse("ok")

    def key_fn(request):
        prefix_calls.append(1)
        return "custom-prefix"

    request = make_request(event, path="/prefix-test/")
    response = etag_cache_page(
        300,
        key_prefix=key_fn,
        request=request,
        request_args=(),
        request_kwargs={},
        handler=handler,
        headers={"X-Frame-Options": "DENY"},
    )

    assert response.status_code == 200
    assert response.has_header("ETag")
    assert response["X-Frame-Options"] == "DENY"
    assert prefix_calls == [1]


@pytest.mark.django_db
def test_etag_cache_page_uncacheable_response_not_stored(event):
    calls = []

    def handler(request):
        calls.append(1)
        return HttpResponse("error", status=500)

    request = make_request(event, path="/uncacheable/")
    first = etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )
    second = etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )

    assert first.status_code == 500
    assert second.status_code == 500
    assert len(calls) == 2


@pytest.mark.django_db
def test_etag_cache_page_regenerated_etag_matches_requested(event):
    def handler(request):
        return HttpResponse("stable content")

    request = make_request(event, path="/regen-etag/")
    first = etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )
    etag_value = first["ETag"].strip('"')

    caches["default"].clear()

    request_with_etag = make_request(
        event, path="/regen-etag/", headers={"If-None-Match": f'"{etag_value}"'}
    )
    response = etag_cache_page(
        300,
        request=request_with_etag,
        request_args=(),
        request_kwargs={},
        handler=handler,
    )

    assert response.status_code == 304


@pytest.mark.django_db
def test_etag_cache_page_skips_etag_generation_when_already_cached(event):
    def handler(request):
        return HttpResponse("content")

    request = make_request(event, path="/etag-cached/")
    first = etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )
    etag_value = first["ETag"].strip('"')

    response_for_key = HttpResponse("content")
    cache_key = learn_cache_key(request, response_for_key, 300, cache=caches["default"])
    caches["default"].delete(cache_key)

    request2 = make_request(event, path="/etag-cached/")
    second = etag_cache_page(
        300, request=request2, request_args=(), request_kwargs={}, handler=handler
    )

    assert second["ETag"].strip('"') == etag_value
