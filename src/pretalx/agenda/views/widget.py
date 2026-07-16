# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import hashlib
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote

from csp.decorators import csp_exempt
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import condition
from i18nfield.utils import I18nJSONEncoder

from pretalx.agenda.rules import is_widget_visible
from pretalx.common.fonts import get_font_css
from pretalx.common.ui import DARK_MODE_TEXT_DARK_MIX, dark_mode_text_override
from pretalx.common.views.cache import conditional_cache_page
from pretalx.schedule.interfaces.widget import build_widget_data

WIDGET_JS_CHECKSUM = None
WIDGET_JS_CONTENT = None
WIDGET_PATH = "agenda/js/pretalx-schedule.min.js"


# Bump whenever event_css generates different output for unchanged event data.
# The ETag is otherwise derived purely from that data, so without this a client
# holding a previously cached event.css would revalidate, be told 304, and keep
# the stale stylesheet forever -- each revalidation refreshes its freshness
# without ever replacing the body.
STYLE_VERSION = "2"


def style_etag(request, event, **kwargs):
    parts = [STYLE_VERSION]
    if color := request.event.primary_color:
        parts.append(f"{color}:{request.event.primary_color_needs_dark_text}")
    heading_font = request.event.display_settings.get("heading_font", "")
    text_font = request.event.display_settings.get("text_font", "")
    if heading_font or text_font:
        parts.append(f"f:{heading_font}:{text_font}")
    if request.GET.get("target") != "orga" and request.event.custom_css:
        parts.append(f"c:{request.event.custom_css.name}")
    # STYLE_VERSION keeps this non-empty, so there is no "no styles" special case.
    return ":".join(parts)


def _load_widget_js():
    global WIDGET_JS_CHECKSUM, WIDGET_JS_CONTENT  # noqa: PLW0603 -- module-level cache for widget JS
    if WIDGET_JS_CONTENT is None:
        file_path = Path(finders.find(WIDGET_PATH))
        with file_path.open(encoding="utf-8") as fp:
            WIDGET_JS_CONTENT = fp.read().encode()
        WIDGET_JS_CHECKSUM = hashlib.md5(WIDGET_JS_CONTENT).hexdigest()  # noqa: S324 -- used for cache busting, not vulnerable to collision attacks


def widget_js_etag(request, event, **kwargs):
    # The widget is stable across all events, we just return a checksum of the JS file
    # to make sure clients reload the widget when it changes.
    _load_widget_js()
    return WIDGET_JS_CHECKSUM


def is_public_and_versioned(request, event, version=None):
    if version and version == "wip":
        # We never cache the wip schedule
        return False
    # This will be either a 404, or a page only accessible to the user
    # due to their logged-in status, so we don't want to cache it.
    return is_widget_visible(None, request.event)


def version_prefix(request, event, version=None):
    """On non-versioned pages, we want cache-invalidation on schedule
    release.
    """
    if not version and request.event.current_schedule:
        return request.event.current_schedule.version
    return version


@conditional_cache_page(
    60,
    key_prefix=version_prefix,
    condition=is_public_and_versioned,
    server_timeout=5 * 60,
    headers={
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Origin": "*",
    },
)
@csp_exempt()
def widget_data(request, event, version=None):
    # Caching this page is tricky: We need the user to occasionally
    # ask for new data, and we definitely need to give them new data on schedule
    # release. This is because some information can change at any time, not just
    # in a new schedule version (like talk titles, speaker info etc).
    # So we:
    #  - tell the user a relatively short cache time that is safe to completely
    #    ignore new data for (1 minute)
    #  - simultaneously build a server-side cache that is invalidated on schedule
    #    release (by using the schedule version as key prefix), and that we keep
    #    around for a longer time (5 minutes), and that will be used for all users
    #  - also save a checksum of this server-side cache, and hand it to the client
    #    as an eTag, so they can ask for new data without it being too expensive
    #    on the server side
    # All this can ONLY take place if the schedule *has* a version (never caching
    # the WIP schedule page), and if anonymous users can see the schedule.
    event = request.event
    if request.method == "OPTIONS":
        response = JsonResponse({})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "authorization,content-type"
        return response
    if not request.user.has_perm("schedule.view_widget_schedule", event):
        raise Http404

    version = version or unquote(request.GET.get("v") or "")
    schedule = None
    if version and version == "wip":
        if not request.user.has_perm("schedule.orga_view_schedule", event):
            raise Http404
        schedule = request.event.wip_schedule
    elif version:
        schedule = event.schedules.filter(version__iexact=version).first()

    schedule = schedule or event.current_schedule
    if not schedule:
        raise Http404

    result = build_widget_data(schedule, all_talks=not schedule.version)
    response = JsonResponse(result, encoder=I18nJSONEncoder)
    response["Access-Control-Allow-Headers"] = "authorization,content-type"
    response["Access-Control-Allow-Origin"] = "*"
    return response


@condition(etag_func=widget_js_etag)
@csp_exempt()
def widget_script(request, event):
    # This page basically just serves a static file under a known path (ideally, the
    # administrators could and should even turn on gzip compression for the
    # /<event>/widget/schedule.js path, as it cuts down the transferred data
    # by about 80% for the schedule.js file, which is the largest file on the
    # main schedule page).
    if not request.user.has_perm("schedule.view_widget_schedule", request.event):
        raise Http404

    _load_widget_js()
    return HttpResponse(WIDGET_JS_CONTENT, content_type="text/javascript")


@condition(etag_func=style_etag)
@cache_page(5 * 60)
@csp_exempt()
def event_css(request, event):
    parts = []
    rules = []
    is_orga = request.GET.get("target") == "orga"
    if color := request.event.primary_color:
        variable = "--color-primary"
        postfix = "-event" if is_orga else ""
        if request.event.primary_color_needs_dark_text:
            rules.append(
                f" --color-text-on-primary{postfix}: var(--color-text-on-light);"
            )
        rules.append(f"{variable}{postfix}: {color};")
    if rules:
        parts.append(":root { " + " ".join(rules) + " }")

    if color and not is_orga:
        # The dark scheme derives its text tokens from --color-primary with a
        # fixed mix toward white, which cannot keep an arbitrary brand colour
        # legible (a dark brand lands around 1.5:1 on the dark background). CSS
        # cannot branch on luminance, so we compute the lift here. This is
        # dark-only on purpose: light mode mixes toward black and is unchanged
        # from upstream, and lifting it would alter light-mode rendering.
        # Orga pages are excluded because there the brand colour is emitted as
        # --color-primary-event, which only paints a border, while
        # --color-primary-text keeps deriving from the default pretalx colour.
        dark_rules = []
        if text_color := dark_mode_text_override(color):
            dark_rules.append(f"--color-primary-text: {text_color};")
        if text_dark := dark_mode_text_override(color, floor=DARK_MODE_TEXT_DARK_MIX):
            dark_rules.append(f"--color-primary-text-dark: {text_dark};")
        if dark_rules:
            parts.append(
                "@media (prefers-color-scheme: dark) { :root { "
                + " ".join(dark_rules)
                + " } }"
            )

    if not is_orga:
        if font_css := get_font_css(request.event):
            parts.append(font_css)
        if request.event.custom_css:
            with suppress(OSError), request.event.custom_css.open("rb") as css_file:
                parts.append(css_file.read().decode())

    result = "\n".join(parts)
    return HttpResponse(result, content_type="text/css")
