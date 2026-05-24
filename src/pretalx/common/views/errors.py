# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import nullcontext

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.urls import get_callable
from django.views import defaults
from django_scopes import scope

from pretalx.common.language import language


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


def handle_404(request, exception=None):
    with language(_language_for_request(request)), _event_scope(request):
        return defaults.page_not_found(request, exception)


def handle_500(request):
    with language(_language_for_request(request)), _event_scope(request):
        return defaults.server_error(request)


def error_view(status_code):
    # The /400, /403, /404, /500 URLs exist so that the error pages can be
    # previewed and tested.
    if status_code == 4031:
        return get_callable(settings.CSRF_FAILURE_VIEW)
    if status_code == 500:
        return handle_500
    handlers = {
        400: (defaults.bad_request, SuspiciousOperation()),
        403: (defaults.permission_denied, PermissionDenied()),
        404: (handle_404, Http404()),
    }
    handler, exception = handlers[status_code]

    def error_view_function(request, *args, **kwargs):
        return handler(request, exception=exception)

    return error_view_function
