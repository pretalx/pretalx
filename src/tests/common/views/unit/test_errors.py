import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.test import override_settings
from django.urls import get_callable

from pretalx.common.views.errors import error_view, handle_500
from tests.utils import make_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_handle_500_with_template(event):
    """When 500.html exists, it renders the HTML error template."""
    request = make_request(event, path="/broken/page/")

    response = handle_500(request)

    assert response.status_code == 500
    assert b"<!DOCTYPE html>" in response.content


@pytest.mark.django_db
def test_handle_500_fallback_when_template_missing(event):
    """When 500.html doesn't exist, the fallback is a plain-text error message."""
    with override_settings(
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": False,
            }
        ]
    ):
        request = make_request(event, path="/broken/")
        response = handle_500(request)

    assert response.status_code == 500
    assert b"Internal server error" in response.content


def test_error_view_500_returns_handle_500():
    assert error_view(500) is handle_500


def test_error_view_4031_returns_csrf_view():
    view = error_view(4031)

    assert view is get_callable(settings.CSRF_FAILURE_VIEW)


@pytest.mark.parametrize(
    ("status_code", "exception"),
    ((400, SuspiciousOperation), (403, PermissionDenied), (404, Http404)),
)
@pytest.mark.django_db
def test_error_view_raises_expected_exception(event, status_code, exception):
    view = error_view(status_code)
    request = make_request(event)

    with pytest.raises(exception):
        view(request)
