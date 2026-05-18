# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import sys

from django.conf import settings
from django.http import Http404
from django.urls import resolve
from django.utils import translation
from django_scopes import get_scope

from pretalx.cfp.signals import footer_link, html_head
from pretalx.common.language import (
    get_day_month_date_format,
    get_javascript_format,
    get_moment_locale,
)
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.text.phrases import phrases


def url_info(request):
    if (
        request.resolver_match
        and set(request.resolver_match.namespaces) & {"orga", "plugins"}
        and not request.user.is_anonymous
    ):
        try:
            url_name = resolve(request.path_info).url_name
        except Http404:
            url_name = ""
        return {"url_name": url_name}
    return {}


def locale_context(request):
    lang = translation.get_language()
    return {
        "js_date_format": get_javascript_format("DATE_INPUT_FORMATS"),
        "js_datetime_format": get_javascript_format("DATETIME_INPUT_FORMATS"),
        "js_locale": get_moment_locale(),
        "quotation_open": phrases.base.quotation_open,
        "quotation_close": phrases.base.quotation_close,
        "DAY_MONTH_DATE_FORMAT": get_day_month_date_format(),
        "rtl": getattr(request, "LANGUAGE_CODE", "en") in settings.LANGUAGES_BIDI,
        "global_primary_color": settings.DEFAULT_EVENT_PRIMARY_COLOR,
        "html_locale": translation.get_language_info(lang).get("public_code", lang),
        "phrases": phrases,
    }


def event_links(request):
    event = getattr(request, "event", None)
    if request.path.startswith("/orga/") or not event or not get_scope():
        return {}

    footer_links = [
        {"label": link.label, "url": link.url}
        for link in event.extra_links.all()
        if link.role == "footer"
    ]
    for _receiver, response in footer_link.send_robust(event, request=request):
        if isinstance(response, list):
            footer_links += response

    header_links = [
        {"label": link.label, "url": link.url}
        for link in event.extra_links.all()
        if link.role == "header"
    ]

    head = "".join(
        response
        for _receiver, response in html_head.send_robust(event, request=request)
        if not isinstance(response, Exception)
    )

    return {
        "footer_links": footer_links,
        "header_links": header_links,
        "html_head": head,
        "has_cfp_submissions": getattr(event, "has_cfp_submissions", False),
    }


def system_warnings(request):
    """Debug-mode info and admin-only update-check warnings."""
    context = {"warning_update_available": False, "warning_update_check_active": False}

    if settings.DEBUG:
        context["development_mode"] = True
        context["pretalx_version"] = settings.PRETALX_VERSION

    if (
        not request.user.is_anonymous
        and request.user.is_administrator
        and request.path.startswith("/orga")
    ):
        gs = GlobalSettings()
        if gs.settings.update_check_result_warning:
            context["warning_update_available"] = True
        if not gs.settings.update_check_ack and "runserver" not in sys.argv:
            context["warning_update_check_active"] = True
    return context
