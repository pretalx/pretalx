# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.urls import resolve
from django.utils import translation
from django.utils.safestring import mark_safe

from pretalx.cfp.signals import footer_link, html_head
from pretalx.common.context_processors import (
    event_links,
    locale_context,
    system_warnings,
    url_info,
)
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.text.phrases import phrases
from tests.factories import EventExtraLinkFactory, EventFactory, UserFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


@pytest.mark.parametrize(
    ("path", "resolved_path", "user", "expected"),
    (
        ("/", None, UserFactory.build(), {}),
        ("/redirect/", "/redirect/", UserFactory.build(), {}),
        ("/orga/login/", "/orga/login/", AnonymousUser(), {}),
        ("/orga/login/", "/orga/login/", UserFactory.build(), {"url_name": "login"}),
        (
            "/orga/this-path-does-not-exist-at-all/",
            "/orga/login/",
            UserFactory.build(),
            {"url_name": ""},
        ),
    ),
    ids=(
        "no_resolver_match",
        "namespace_not_orga",
        "anonymous",
        "orga_namespace",
        "unresolvable_path",
    ),
)
def test_url_info(path, resolved_path, user, expected):
    request = rf.get(path)
    request.resolver_match = resolved_path and resolve(resolved_path)
    request.user = user

    assert url_info(request) == expected


def test_locale_context_returns_expected_keys():
    request = rf.get("/")
    request.LANGUAGE_CODE = "en"

    result = locale_context(request)

    assert set(result.keys()) == {
        "js_date_format",
        "js_datetime_format",
        "js_locale",
        "js_short_date_format",
        "quotation_open",
        "quotation_close",
        "DAY_MONTH_DATE_FORMAT",
        "rtl",
        "global_primary_color",
        "html_locale",
        "phrases",
    }
    assert result["phrases"] is phrases
    assert result["rtl"] is False


@pytest.mark.parametrize(
    ("language", "expected"), (("en", "Y-m-d"), ("de", "d.m.Y"), ("nl", "j-n-Y"))
)
def test_locale_context_exposes_django_short_date_format(language, expected):
    request = rf.get("/")
    request.LANGUAGE_CODE = language

    with translation.override(language):
        result = locale_context(request)

    assert result["js_short_date_format"] == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    (
        ("en", "en"),
        ("de", "de"),
        ("de-formal", "de"),
        ("zh-hans", "zh-Hans"),
        ("zh-hant", "zh-Hant"),
        ("pt-br", "pt-BR"),
        ("pt-pt", "pt-PT"),
    ),
)
def test_locale_context_exposes_a_valid_language_tag(language, expected):
    request = rf.get("/")
    request.LANGUAGE_CODE = language

    with translation.override(language):
        result = locale_context(request)

    assert result["html_locale"] == expected


@override_settings(LANGUAGES_BIDI=["ar", "he"])
def test_locale_context_rtl_true_for_bidi_language():
    request = rf.get("/")
    request.LANGUAGE_CODE = "ar"

    result = locale_context(request)

    assert result["rtl"] is True


@pytest.mark.parametrize(
    "path", ("/some/public/page/", "/orga/login/"), ids=("public", "orga")
)
def test_event_links_returns_empty_without_event(path):
    request = rf.get(path)
    request.user = AnonymousUser()

    assert event_links(request) == {}


@pytest.mark.django_db
def test_event_links_orga_path_with_event_returns_empty(event):
    request = rf.get("/orga/login/")
    request.user = AnonymousUser()
    request.event = event

    assert event_links(request) == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("response", "expected"),
    (
        (
            [{"label": "Link1", "url": "/1"}, {"label": "Link2", "url": "/2"}],
            [{"label": "Link1", "url": "/1"}, {"label": "Link2", "url": "/2"}],
        ),
        ({"label": "Old-style", "url": "/old"}, []),
    ),
    ids=("list", "non_list_ignored"),
)
def test_event_links_footer_link_signal(register_signal_handler, response, expected):
    def handler(signal, sender, **kwargs):
        return response

    register_signal_handler(footer_link, handler)

    event = EventFactory()
    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    assert event_links(request)["footer_links"] == expected


@pytest.mark.django_db
def test_event_links_includes_extra_links_with_event_and_scope():
    event = EventFactory()
    EventExtraLinkFactory(
        event=event, label="Footer", url="https://footer.example.com", role="footer"
    )
    EventExtraLinkFactory(
        event=event, label="Header", url="https://header.example.com", role="header"
    )

    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    result = event_links(request)

    assert result["footer_links"] == [
        {"label": "Footer", "url": "https://footer.example.com"}
    ]
    assert result["header_links"] == [
        {"label": "Header", "url": "https://header.example.com"}
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("response", "expected"),
    (
        pytest.param(
            mark_safe("<style>body{}</style>"),
            "<style>body{}</style>",
            id="safe_string_unchanged",
        ),
        pytest.param(
            "<script>alert(1)</script>",
            "&lt;script&gt;alert(1)&lt;/script&gt;",
            id="plain_string_escaped",
        ),
        pytest.param(None, "", id="none_dropped"),
        pytest.param(
            [mark_safe("<style></style>"), "<b>x</b>", None],
            "<style></style>&lt;b&gt;x&lt;/b&gt;",
            id="list_escaped_per_item",
        ),
    ),
)
def test_event_links_html_head_signal_with_event(
    register_signal_handler, response, expected
):
    def handler(signal, sender, **kwargs):
        return response

    register_signal_handler(html_head, handler)

    event = EventFactory()

    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    result = event_links(request)

    assert result["html_head"] == expected


@pytest.mark.django_db
def test_event_links_skips_signal_exceptions(register_signal_handler):
    def boom(signal, sender, **kwargs):
        raise RuntimeError("plugin exploded")

    register_signal_handler(footer_link, boom)
    register_signal_handler(html_head, boom)

    event = EventFactory()
    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    result = event_links(request)

    assert result["footer_links"] == []
    assert result["html_head"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "make_user"),
    (
        ("/", AnonymousUser),
        ("/orga/admin/", lambda: UserFactory(is_administrator=False)),
    ),
    ids=("anonymous", "non_admin_on_orga_path"),
)
def test_system_warnings_without_admin_shows_no_update_warnings(path, make_user):
    request = rf.get(path)
    request.user = make_user()

    result = system_warnings(request)

    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False


def test_system_warnings_without_user_attribute():
    # Error pages can render before AuthenticationMiddleware has set request.user.
    request = rf.get("/orga/admin/")

    result = system_warnings(request)

    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False


@pytest.mark.parametrize(
    ("debug", "expected"),
    (
        (True, {"development_mode": True, "pretalx_version": "test-version"}),
        (False, {}),
    ),
    ids=("debug_adds_development_info", "no_debug_omits_it"),
)
def test_system_warnings_development_info(settings, debug, expected):
    settings.DEBUG = debug
    settings.PRETALX_VERSION = "test-version"
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_warnings(request)

    assert {
        key: value
        for key, value in result.items()
        if key in ("development_mode", "pretalx_version")
    } == expected


@pytest.mark.parametrize(
    ("enabled", "warning_result", "ack", "expected_available", "expected_active"),
    (
        (True, True, True, True, False),
        (True, False, False, False, True),
        (False, True, True, False, False),
    ),
    ids=["available", "acked", "check-disabled"],
)
@pytest.mark.django_db
def test_system_warnings_admin_user_update_warnings(
    enabled, warning_result, ack, expected_available, expected_active
):
    user = UserFactory(is_administrator=True)

    request = rf.get("/orga/admin/")
    request.user = user

    gs = GlobalSettings()
    gs.settings.set("update_check_enabled", enabled)
    gs.settings.set("update_check_result_warning", warning_result)
    gs.settings.set("update_check_ack", ack)

    result = system_warnings(request)

    assert result["warning_update_available"] is expected_available
    assert result["warning_update_check_active"] is expected_active
