# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.conf import settings
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.translation.trans_real import (
    get_supported_language_variant,
    parse_accept_lang_header,
)


def validate_language(value, supported):
    with suppress(LookupError):
        value = get_supported_language_variant(value)
        if value in supported:
            return value


def get_language_from_query(request, supported):
    lang = request.GET.get("lang")
    if lang:
        lang = validate_language(lang, supported)
        if lang:
            request.COOKIES[settings.LANGUAGE_COOKIE_NAME] = lang
            return lang


def get_language_from_user(request, supported):
    if request.user.is_authenticated:
        return validate_language(request.user.locale, supported)


def get_language_from_cookie(request, supported):
    cookie_value = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    return validate_language(cookie_value, supported)


def get_language_from_browser(request, supported):
    accept_value = request.headers.get("Accept-Language", "")
    for accept_lang, _ in parse_accept_lang_header(accept_value):
        if accept_lang == "*":
            break

        validated = validate_language(accept_lang, supported)
        if validated:
            return validated


def get_language_from_event(request, supported):
    if getattr(request, "event", None):
        return validate_language(request.event.locale, supported)


def get_language_from_early_request(request):
    supported = list(settings.LANGUAGES_INFORMATION)
    return (
        get_language_from_cookie(request, supported)
        or get_language_from_browser(request, supported)
        or settings.LANGUAGE_CODE
    )


class LocaleMiddleware:
    """
    First part of locale selection, using only data contained in the
    request itself (not user object, event object etc), so that we
    can handle error pages as well as possible.
    The remainder of the language wrangling happens when we have the
    rest of the information, in EventMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        translation.activate(get_language_from_early_request(request))
        request.LANGUAGE_CODE = translation.get_language()
        timezone.deactivate()

        response = self.get_response(request)

        patch_vary_headers(response, ("Accept-Language",))
        if "Content-Language" not in response:
            response["Content-Language"] = translation.get_language()
        return response
