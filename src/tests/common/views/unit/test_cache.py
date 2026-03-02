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

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("locmem_cache")]


@pytest.mark.django_db
def test_get_requested_etag_present(event):
    request = make_request(event, headers={"If-None-Match": '"abc123"'})

    assert get_requested_etag(request) == "abc123"


@pytest.mark.django_db
def test_get_requested_etag_missing(event):
    request = make_request(event)

    assert get_requested_etag(request) is None


def test_get_etag_bytes_content():
    response = HttpResponse(b"hello world")

    etag = get_etag(response)

    assert len(etag) == 32  # MD5 hex digest


def test_get_etag_same_content_same_hash():
    r1 = HttpResponse(b"identical")
    r2 = HttpResponse(b"identical")

    assert get_etag(r1) == get_etag(r2)


def test_get_etag_different_content_different_hash():
    r1 = HttpResponse(b"content-a")
    r2 = HttpResponse(b"content-b")

    assert get_etag(r1) != get_etag(r2)


def test_get_etag_string_content():
    """String content is encoded to bytes before hashing."""
    response = HttpResponse("text content")

    etag = get_etag(response)

    assert len(etag) == 32


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
def test_should_cache_private_cache_control(event):
    request = make_request(event)
    response = HttpResponse("ok")
    response["Cache-Control"] = "private"

    assert should_cache(request, response) is False


@pytest.mark.django_db
def test_should_cache_false_when_response_sets_cookie_with_vary(event):
    """Responses setting cookies with Vary: Cookie header should not be cached
    when the request has no cookies."""
    request = make_request(event)
    response = HttpResponse("ok")
    response.set_cookie("session", "abc")
    response["Vary"] = "Cookie"

    assert should_cache(request, response) is False


def test_patched_response_sets_cache_headers():
    response = HttpResponse("ok")

    result = patched_response(response, 300)

    assert "max-age=300" in result["Cache-Control"]


def test_patched_response_sets_custom_headers():
    response = HttpResponse("ok")

    result = patched_response(response, 300, headers={"X-Custom": "value"})

    assert result["X-Custom"] == "value"


def test_patched_response_returns_same_response():
    response = HttpResponse("ok")

    result = patched_response(response, 300)

    assert result is response


@pytest.mark.django_db
def test_conditional_cache_page_skips_non_get(event):
    """POST requests bypass the cache entirely."""
    calls = []

    @conditional_cache_page(300)
    def view(request):
        calls.append(1)
        return HttpResponse("ok")

    request = make_request(event, method="post", path="/test/")
    view(request)
    view(request)

    assert len(calls) == 2


@pytest.mark.django_db
def test_conditional_cache_page_skips_when_condition_false(event):
    """When condition returns False, handler runs without caching."""
    calls = []

    @conditional_cache_page(300, condition=lambda req: False)
    def view(request):
        calls.append(1)
        return HttpResponse("ok")

    request = make_request(event, path="/test/")
    view(request)
    view(request)

    assert len(calls) == 2


@pytest.mark.django_db
def test_conditional_cache_page_caches_get_request(event):
    """GET requests with condition met are cached — handler runs only once."""
    calls = []

    @conditional_cache_page(300)
    def view(request):
        calls.append(1)
        return HttpResponse("cached")

    request = make_request(event, path="/cache-get/")
    first = view(request)
    second = view(request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1


@pytest.mark.django_db
def test_etag_cache_page_caches_response(event):
    """First request caches the response, second returns it from cache."""
    calls = []

    def handler(request):
        calls.append(1)
        return HttpResponse("cached content")

    request = make_request(event, path="/cacheable/")
    etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )
    etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )

    assert len(calls) == 1


@pytest.mark.django_db
def test_etag_cache_page_returns_304_on_matching_etag(event):
    """When client sends a matching ETag, returns 304 Not Modified."""

    def handler(request):
        return HttpResponse("content")

    request = make_request(event, path="/etag-test/")
    first_response = etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )
    etag_value = first_response["ETag"].strip('"')

    request_with_etag = make_request(
        event, path="/etag-test/", headers={"If-None-Match": f'"{etag_value}"'}
    )
    second_response = etag_cache_page(
        300,
        request=request_with_etag,
        request_args=(),
        request_kwargs={},
        handler=handler,
    )

    assert second_response.status_code == 304


@pytest.mark.django_db
def test_etag_cache_page_callable_key_prefix(event):
    """A callable key_prefix is invoked and the response is cached normally."""
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
    )

    assert response.status_code == 200
    assert response.has_header("ETag")
    assert len(prefix_calls) == 1


@pytest.mark.django_db
def test_etag_cache_page_custom_headers(event):
    """Custom headers are applied to the response."""

    def handler(request):
        return HttpResponse("ok")

    request = make_request(event, path="/headers-test/")
    response = etag_cache_page(
        300,
        request=request,
        request_args=(),
        request_kwargs={},
        handler=handler,
        headers={"X-Frame-Options": "DENY"},
    )

    assert response["X-Frame-Options"] == "DENY"


@pytest.mark.django_db
def test_etag_cache_page_server_timeout(event):
    """A custom server_timeout is accepted and the response is cached."""
    calls = []

    def handler(request):
        calls.append(1)
        return HttpResponse("ok")

    request = make_request(event, path="/timeout-test/")
    etag_cache_page(
        60,
        server_timeout=120,
        request=request,
        request_args=(),
        request_kwargs={},
        handler=handler,
    )
    etag_cache_page(
        60,
        server_timeout=120,
        request=request,
        request_args=(),
        request_kwargs={},
        handler=handler,
    )

    assert len(calls) == 1


@pytest.mark.django_db
def test_etag_cache_page_mismatched_etag_returns_full_response(event):
    """When client sends a stale ETag, the full response is returned."""

    def handler(request):
        return HttpResponse("new content")

    request = make_request(event, path="/stale-etag/")
    etag_cache_page(
        300, request=request, request_args=(), request_kwargs={}, handler=handler
    )

    request_stale = make_request(
        event, path="/stale-etag/", headers={"If-None-Match": '"stale-etag-value"'}
    )
    response = etag_cache_page(
        300, request=request_stale, request_args=(), request_kwargs={}, handler=handler
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_etag_cache_page_uncacheable_response_not_stored(event):
    """Responses that fail should_cache are returned but not cached."""
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
    """When the cache forgets the ETag but the regenerated content matches
    the requested ETag, a 304 is returned."""

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
    """When the etag is still in cache but the response was evicted, the
    existing etag is reused instead of being regenerated."""

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
