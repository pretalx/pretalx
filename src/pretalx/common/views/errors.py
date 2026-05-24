# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import urllib
from contextlib import suppress

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpResponseServerError
from django.template import TemplateDoesNotExist, loader
from django.urls import get_callable
from django.views import defaults


def handle_500(request):
    try:
        template = loader.get_template("500.html")
    except TemplateDoesNotExist:
        return HttpResponseServerError(
            "Internal server error. Please contact the administrator for details.",
            content_type="text/html",
        )
    context = {"request": request}
    with suppress(
        Exception
    ):  # This should never fail, but can't be too cautious in error views
        context["request_path"] = urllib.parse.quote(request.path)
    return HttpResponseServerError(template.render(context))


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
        404: (defaults.page_not_found, Http404()),
    }
    handler, exception = handlers[status_code]

    def error_view_function(request, *args, **kwargs):
        return handler(request, exception=exception)

    return error_view_function
