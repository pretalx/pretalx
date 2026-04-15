# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import urllib.parse

from django.core import signing
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html


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
