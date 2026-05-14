# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.urls import resolve

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


def test_url_info_empty_when_no_resolver_match():
    request = rf.get("/")
    request.resolver_match = None
    request.user = UserFactory.build()

    assert url_info(request) == {}


def test_url_info_empty_when_namespace_not_orga_or_plugins():
    request = rf.get("/redirect/")
    request.resolver_match = resolve("/redirect/")
    request.user = UserFactory.build()

    assert url_info(request) == {}


def test_url_info_empty_when_user_is_anonymous():
    request = rf.get("/orga/login/")
    request.resolver_match = resolve("/orga/login/")
    request.user = AnonymousUser()

    assert url_info(request) == {}


def test_url_info_returns_url_info_for_orga_namespace():
    request = rf.get("/orga/login/")
    request.resolver_match = resolve("/orga/login/")
    request.user = UserFactory.build()

    result = url_info(request)

    assert result == {"url_name": "login"}


def test_url_info_returns_empty_strings_on_unresolvable_path():
    request = rf.get("/orga/this-path-does-not-exist-at-all/")
    request.resolver_match = resolve("/orga/login/")
    request.user = UserFactory.build()

    result = url_info(request)

    assert result == {"url_name": ""}


def test_locale_context_returns_expected_keys():
    request = rf.get("/")
    request.LANGUAGE_CODE = "en"

    result = locale_context(request)

    assert set(result.keys()) == {
        "js_date_format",
        "js_datetime_format",
        "js_locale",
        "quotation_open",
        "quotation_close",
        "DAY_MONTH_DATE_FORMAT",
        "rtl",
        "global_primary_color",
        "html_locale",
        "phrases",
    }


def test_locale_context_includes_phrases():
    request = rf.get("/")
    request.LANGUAGE_CODE = "en"

    result = locale_context(request)

    assert result["phrases"] is phrases


def test_locale_context_rtl_false_for_english():
    request = rf.get("/")
    request.LANGUAGE_CODE = "en"

    result = locale_context(request)

    assert result["rtl"] is False


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
def test_event_links_signal_handler_returning_list(register_signal_handler):
    links = [{"label": "Link1", "url": "/1"}, {"label": "Link2", "url": "/2"}]

    def handler(signal, sender, **kwargs):
        return links

    register_signal_handler(footer_link, handler)

    event = EventFactory()
    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    result = event_links(request)

    assert result["footer_links"] == links


@pytest.mark.django_db
def test_event_links_signal_handler_returning_non_list_is_ignored(
    register_signal_handler,
):
    """A footer_link handler returning anything but a list is silently dropped."""

    def handler(signal, sender, **kwargs):
        return {"label": "Old-style", "url": "/old"}

    register_signal_handler(footer_link, handler)

    event = EventFactory()
    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    assert event_links(request)["footer_links"] == []


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
def test_event_links_html_head_signal_with_event(register_signal_handler):
    """html_head signal responses are concatenated into context['html_head']."""

    def handler(signal, sender, **kwargs):
        return "<style>body{}</style>"

    register_signal_handler(html_head, handler)

    event = EventFactory()

    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    result = event_links(request)

    assert result["html_head"] == "<style>body{}</style>"


@pytest.mark.django_db
def test_event_links_skips_signal_exceptions(register_signal_handler):
    """A plugin raising in footer_link/html_head must not break rendering."""

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


def test_system_warnings_non_admin_defaults():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_warnings(request)

    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False


@override_settings(DEBUG=True, PRETALX_VERSION="test-version")
def test_system_warnings_debug_mode_adds_development_info():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_warnings(request)

    assert result["development_mode"] is True
    assert result["pretalx_version"] == "test-version"


@override_settings(DEBUG=False)
def test_system_warnings_no_debug_omits_development_mode():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_warnings(request)

    assert "development_mode" not in result


@pytest.mark.parametrize(
    ("warning_result", "ack", "expected_available", "expected_active"),
    ((True, True, True, False), (False, False, False, True)),
)
@pytest.mark.django_db
def test_system_warnings_admin_user_update_warnings(
    warning_result, ack, expected_available, expected_active
):
    user = UserFactory(is_administrator=True)

    request = rf.get("/orga/admin/")
    request.user = user

    gs = GlobalSettings()
    gs.settings.set("update_check_result_warning", warning_result)
    gs.settings.set("update_check_ack", ack)

    result = system_warnings(request)

    assert result["warning_update_available"] is expected_available
    assert result["warning_update_check_active"] is expected_active


@pytest.mark.django_db
def test_system_warnings_non_admin_on_orga_path_no_warnings():
    user = UserFactory(is_administrator=False)

    request = rf.get("/orga/admin/")
    request.user = user

    result = system_warnings(request)

    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False
