import pytest
from django.http import Http404
from django.test import RequestFactory

from pretalx.common.views.helpers import (
    get_htmx_target,
    get_static,
    is_form_bound,
    is_htmx,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

_rf = RequestFactory()


@pytest.mark.parametrize(
    ("method", "post_data", "form_name", "form_param", "expected"),
    (
        ("POST", {"form": "myform"}, "myform", "form", True),
        ("POST", {"form": "other"}, "myform", "form", False),
        ("POST", {}, "myform", "form", False),
        ("GET", {}, "myform", "form", False),
        ("POST", {"action": "myform"}, "myform", "action", True),
    ),
    ids=(
        "matching_param",
        "wrong_param",
        "missing_param",
        "get_request",
        "custom_form_param",
    ),
)
def test_is_form_bound(method, post_data, form_name, form_param, expected):
    request = _rf.generic(method, "/")
    request.POST = post_data
    assert is_form_bound(request, form_name, form_param=form_param) is expected


def test_get_static_missing_file_raises_404():
    with pytest.raises(Http404):
        get_static("nonexistent/file.css", "text/css")


@pytest.mark.parametrize(
    ("headers", "expected"),
    (({"HX-Request": "true"}, True), ({}, False)),
    ids=("with_header", "without_header"),
)
def test_is_htmx(headers, expected):
    request = _rf.get("/", headers=headers)
    assert is_htmx(request) is expected


@pytest.mark.parametrize(
    ("headers", "expected"),
    (({"HX-Target": "my-target"}, "my-target"), ({}, "")),
    ids=("with_header", "without_header"),
)
def test_get_htmx_target(headers, expected):
    request = _rf.get("/", headers=headers)
    assert get_htmx_target(request) == expected
