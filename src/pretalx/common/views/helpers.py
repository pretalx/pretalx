# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import urlparse

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import FileResponse, Http404, HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme


def is_form_bound(request, form_name, form_param="form"):
    return request.method == "POST" and request.POST.get(form_param) == form_name


def get_static(path, content_type, as_attachment=False, filename=None):
    try:
        return FileResponse(
            staticfiles_storage.open(path),
            content_type=content_type,
            as_attachment=as_attachment,
            filename=filename,
        )
    except (OSError, ValueError):
        raise Http404 from None


def is_htmx(request):
    return bool(request.headers.get("HX-Request"))


def get_htmx_target(request):
    return request.headers.get("HX-Target") or ""


def get_htmx_current_url(request):
    url = request.headers.get("HX-Current-URL")
    if not url or not url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return None
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def htmx_redirect(url):
    """Tell HTMX to navigate to the redirect URL rather than following and rendering it."""
    response = HttpResponse(status=286)
    response["HX-Redirect"] = str(url)
    return response
