# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import urllib.parse
from urllib.parse import quote

from django.core import signing
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme


def _is_samesite_referer(request):
    referer = request.headers.get("referer")
    if referer is None:
        return False

    referer = urllib.parse.urlparse(referer)

    # Make sure we have a valid URL for Referer.
    if "" in (referer.scheme, referer.netloc):
        return False

    return (referer.scheme, referer.netloc) == (request.scheme, request.get_host())


def redirect_view(request):
    signer = signing.Signer(salt="safe-redirect")
    try:
        url = signer.unsign(request.GET.get("url", ""))
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid parameter")

    # We block javascript:, data: etc
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme and scheme not in ("http", "https", "ftp", "ftps"):
        return HttpResponseBadRequest("Invalid parameter")

    if not _is_samesite_referer(request):
        hostname = urllib.parse.urlparse(url).hostname or ""
        host = format_html("<strong>{}</strong>", hostname)
        return render(
            request,
            "common/redirect.html",
            {"hostname": hostname, "host": host, "url": url},
        )
    return HttpResponseRedirect(url)


def safelink(url):
    signer = signing.Signer(salt="safe-redirect")
    return reverse("redirect") + "?url=" + urllib.parse.quote(signer.sign(url))


def get_next_url(request, omit_params=None):
    params = request.GET.copy()
    omit_params = omit_params or []
    for param in omit_params:
        params.pop(param, None)
    if not (url := params.pop("next", [""])[0]):
        return
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        return
    if params:
        return f"{url}?{params.urlencode()}"
    return url


def build_login_redirect_url(
    event, return_path, *, fragment=None, orga=False, absolute=False, extra_params=""
):
    if event is None:
        login_url = reverse("orga:login")
    else:
        url = event.orga_urls.login if orga else event.urls.login
        login_url = url.full() if absolute else str(url)
    if fragment:
        return_path = f"{return_path}#{fragment}"
    result = f"{login_url}?next={quote(return_path)}"
    if extra_params:
        result = f"{result}&{extra_params}"
    return result


def get_login_redirect(request):
    """Get a redirect to the best choice of login pages with
    ?next= pointing at the current path (or an exising ?next).
    """
    params = request.GET.copy()
    next_url = params.pop("next", [request.path])[0] or request.path
    return redirect(
        build_login_redirect_url(
            getattr(request, "event", None),
            next_url,
            orga=request.path.startswith("/orga"),
            absolute=True,
            extra_params=params.urlencode(),
        )
    )
