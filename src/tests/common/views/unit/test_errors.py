# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import get_callable
from django.urls.exceptions import Resolver404
from django.utils import translation

from pretalx.common.views.errors import error_view, handle_404, handle_500
from tests.utils import make_request

pytestmark = pytest.mark.unit


HANDLERS = pytest.mark.parametrize(
    ("handler", "status_code"),
    ((handle_404, 404), (handle_500, 500)),
    ids=("404", "500"),
)


@HANDLERS
@pytest.mark.django_db
def test_handler_renders_html_template(event, handler, status_code):
    request = make_request(event, path="/broken/page/")

    response = handler(request)

    assert response.status_code == status_code
    assert b"<!DOCTYPE html>" in response.content


@pytest.mark.parametrize(
    ("handler", "status_code", "expected"),
    ((handle_404, 404, b"Not Found"), (handle_500, 500, b"Server Error")),
    ids=("404", "500"),
)
@pytest.mark.django_db
def test_handler_fallback_when_template_missing(event, handler, status_code, expected):
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
        response = handler(request)

    assert response.status_code == status_code
    assert expected in response.content


@HANDLERS
@pytest.mark.django_db
def test_handler_renders_event_button_for_public_event(event, handler, status_code):
    request = make_request(event, path=f"/{event.slug}/broken")

    response = handler(request)

    assert response.status_code == status_code
    content = response.content.decode()
    # RequestContext-driven chrome: event button + shared footer must render,
    # which confirms context processors ran.
    assert "Event home" in content
    assert event.urls.base in content
    assert "Contact us" in content


@HANDLERS
@pytest.mark.django_db
def test_handler_hides_event_button_for_nonpublic_event(event, handler, status_code):
    event.is_public = False
    event.save()
    request = make_request(event, path=f"/{event.slug}/broken")

    response = handler(request)

    assert response.status_code == status_code
    content = response.content.decode()
    assert event.urls.base not in content
    assert "Event home" not in content


@pytest.mark.parametrize(
    ("handler", "status_code", "expected_phrase"),
    (
        (handle_404, 404, "Page not found"),
        (handle_500, 500, "We have encountered an error"),
    ),
    ids=("404", "500"),
)
@pytest.mark.django_db
def test_handler_uses_event_locale_when_middleware_did_not_run(
    event, handler, status_code, expected_phrase
):
    # Leave a stale language activated to simulate a previous request
    # on the same worker.
    translation.activate("de")
    try:
        event.locale = "en"
        event.save()
        request = make_request(event, path=f"/{event.slug}/broken")

        response = handler(request)

        assert response.status_code == status_code
        # If language activation worked, the phrase is English; if it
        # leaked from the stale state, it would be German.
        assert expected_phrase in response.content.decode()
    finally:
        translation.deactivate()


@pytest.mark.django_db
def test_handle_404_without_event(event):
    request = make_request(event, path="/totally/missing")
    request.event = None

    response = handle_404(request)

    assert response.status_code == 404
    # Even without an event, the page heading still renders.
    assert "Page not found" in response.content.decode()


@pytest.mark.django_db
def test_handle_404_sanitizes_resolver404_exception(event):
    request = make_request(event, path="/missing/")
    exception = Resolver404({"path": "/missing/", "tried": [["some-pattern"]]})

    response = handle_404(request, exception=exception)

    assert response.status_code == 404
    assert b"some-pattern" not in response.content
    assert b"tried" not in response.content


def test_error_view_500_returns_handle_500():
    assert error_view(500) is handle_500


def test_error_view_4031_returns_csrf_view():
    view = error_view(4031)

    assert view is get_callable(settings.CSRF_FAILURE_VIEW)


@pytest.mark.parametrize("status_code", (400, 403, 404))
@pytest.mark.django_db
def test_error_view_renders_template_without_raising(event, status_code):
    view = error_view(status_code)
    request = make_request(event)

    response = view(request)

    assert response.status_code == status_code
    assert b"<!DOCTYPE html>" in response.content
