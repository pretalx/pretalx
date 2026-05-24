# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import nullcontext

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpResponseServerError
from django.template import TemplateDoesNotExist, loader
from django.views import csrf, defaults
from django_scopes import scope

from pretalx.common.language import language

ERROR_500_TEMPLATE_NAME = "500.html"


def _event_scope(request):
    event = getattr(request, "event", None)
    return scope(event=event) if event else nullcontext()


def _language_for_request(request):
    lang = getattr(request, "LANGUAGE_CODE", None)
    if lang:
        return lang
    event = getattr(request, "event", None)
    if event and event.locale:
        return event.locale
    return settings.LANGUAGE_CODE


def _render_in_event_context(request, render):
    with language(_language_for_request(request)), _event_scope(request):
        return render()


def handle_400(request, exception=None):
    return _render_in_event_context(
        request, lambda: defaults.bad_request(request, exception)
    )


def handle_403(request, exception=None):
    return _render_in_event_context(
        request, lambda: defaults.permission_denied(request, exception)
    )


def handle_404(request, exception=None):
    return _render_in_event_context(
        request, lambda: defaults.page_not_found(request, exception)
    )


def handle_500(request):
    # Unlike defaults.server_error, we pass the request to template.render so
    # context processors run and the page picks up request.event, footer
    # links, and locale-driven phrases.
    def render():
        try:
            template = loader.get_template(ERROR_500_TEMPLATE_NAME)
        except TemplateDoesNotExist:
            return defaults.server_error(request)
        return HttpResponseServerError(template.render(request=request))

    return _render_in_event_context(request, render)


def handle_csrf_failure(request, reason=""):
    return _render_in_event_context(request, lambda: csrf.csrf_failure(request, reason))


def error_view(status_code):
    # The /400, /403, /404, /500 URLs exist so that the error pages can be
    # previewed and tested.
    if status_code == 4031:
        return handle_csrf_failure
    if status_code == 500:
        return handle_500
    handlers = {
        400: (handle_400, SuspiciousOperation()),
        403: (handle_403, PermissionDenied()),
        404: (handle_404, Http404()),
    }
    handler, exception = handlers[status_code]

    def error_view_function(request, *args, **kwargs):
        return handler(request, exception=exception)

    return error_view_function
