import warnings

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.urls import resolve
from django_scopes import scopes_disabled

from pretalx.cfp.signals import footer_link, html_head
from pretalx.common.context_processors import (
    add_events,
    get_day_month_date_format,
    locale_context,
    messages,
    system_information,
)
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.text.phrases import phrases
from pretalx.event.models.event import EventExtraLink
from tests.factories import EventFactory, UserFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


def test_add_events_empty_when_no_resolver_match():
    request = rf.get("/")
    request.resolver_match = None
    request.user = UserFactory.build()

    assert add_events(request) == {}


def test_add_events_empty_when_namespace_not_orga_or_plugins():
    request = rf.get("/redirect/")
    request.resolver_match = resolve("/redirect/")
    request.user = UserFactory.build()

    assert add_events(request) == {}


def test_add_events_empty_when_user_is_anonymous():
    request = rf.get("/orga/login/")
    request.resolver_match = resolve("/orga/login/")
    request.user = AnonymousUser()

    assert add_events(request) == {}


def test_add_events_returns_url_info_for_orga_namespace():
    request = rf.get("/orga/login/")
    request.resolver_match = resolve("/orga/login/")
    request.user = UserFactory.build()

    result = add_events(request)

    assert result == {"url_name": "login", "url_namespace": "orga"}


def test_add_events_returns_empty_strings_on_unresolvable_path():
    """When the path doesn't resolve, url_name and url_namespace are empty."""
    request = rf.get("/orga/this-path-does-not-exist-at-all/")
    request.resolver_match = resolve("/orga/login/")
    request.user = UserFactory.build()

    result = add_events(request)

    assert result == {"url_name": "", "url_namespace": ""}


def test_get_day_month_date_format_excludes_year():
    result = get_day_month_date_format()

    assert isinstance(result, str)
    assert "Y" not in result


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
    }


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


def test_messages_returns_phrases():
    request = rf.get("/")

    result = messages(request)

    assert result == {"phrases": phrases}


def test_system_information_non_orga_path_defaults():
    request = rf.get("/some/public/page/")
    request.user = AnonymousUser()

    result = system_information(request)

    assert result["footer_links"] == []
    assert result["header_links"] == []
    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False


def test_system_information_orga_path_omits_footer_and_header_links():
    request = rf.get("/orga/login/")
    request.user = AnonymousUser()

    result = system_information(request)

    assert "footer_links" not in result
    assert "header_links" not in result


@override_settings(DEBUG=True, PRETALX_VERSION="test-version")
def test_system_information_debug_mode_adds_development_info():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_information(request)

    assert result["development_mode"] is True
    assert result["pretalx_version"] == "test-version"


@override_settings(DEBUG=False)
def test_system_information_no_debug_omits_development_mode():
    request = rf.get("/")
    request.user = AnonymousUser()

    result = system_information(request)

    assert "development_mode" not in result


def test_system_information_signal_handler_returning_list(register_signal_handler):
    """When a footer_link signal handler returns a list, its items are added."""
    links = [{"label": "Link1", "url": "/1"}, {"label": "Link2", "url": "/2"}]

    def handler(signal, sender, **kwargs):
        return links

    register_signal_handler(footer_link, handler)

    request = rf.get("/some/page/")
    request.user = AnonymousUser()

    result = system_information(request)

    assert result["footer_links"] == links


def test_system_information_signal_handler_returning_dict_warns(
    register_signal_handler,
):
    """When a footer_link signal handler returns a dict instead of a list,
    it is appended but a DeprecationWarning is issued."""
    link = {"label": "Old-style", "url": "/old"}

    def handler(signal, sender, **kwargs):
        return link

    register_signal_handler(footer_link, handler)

    request = rf.get("/some/page/")
    request.user = AnonymousUser()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = system_information(request)

    assert result["footer_links"] == [link]
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


@pytest.mark.django_db
def test_system_information_includes_extra_links_with_event_and_scope():
    with scopes_disabled():
        event = EventFactory()
        EventExtraLink.objects.create(
            event=event, label="Footer", url="https://footer.example.com", role="footer"
        )
        EventExtraLink.objects.create(
            event=event, label="Header", url="https://header.example.com", role="header"
        )

    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    with scopes_disabled():
        result = system_information(request)

    assert result["footer_links"] == [
        {"label": "Footer", "url": "https://footer.example.com"}
    ]
    assert result["header_links"] == [
        {"label": "Header", "url": "https://header.example.com"}
    ]


@pytest.mark.django_db
def test_system_information_html_head_signal_with_event(register_signal_handler):
    """html_head signal responses are concatenated into context['html_head']."""

    def handler(signal, sender, **kwargs):
        return "<style>body{}</style>"

    register_signal_handler(html_head, handler)

    with scopes_disabled():
        event = EventFactory()

    request = rf.get("/some/page/")
    request.user = AnonymousUser()
    request.event = event

    with scopes_disabled():
        result = system_information(request)

    assert result["html_head"] == "<style>body{}</style>"


@pytest.mark.parametrize(
    ("warning_result", "ack", "expected_available", "expected_active"),
    ((True, True, True, False), (False, False, False, True)),
)
@pytest.mark.django_db
def test_system_information_admin_user_update_warnings(
    warning_result, ack, expected_available, expected_active
):
    user = UserFactory(is_administrator=True)

    request = rf.get("/orga/admin/")
    request.user = user

    gs = GlobalSettings()
    gs.settings.set("update_check_result_warning", warning_result)
    gs.settings.set("update_check_ack", ack)

    result = system_information(request)

    assert result["warning_update_available"] is expected_available
    assert result["warning_update_check_active"] is expected_active


@pytest.mark.django_db
def test_system_information_non_admin_on_orga_path_no_warnings():
    user = UserFactory(is_administrator=False)

    request = rf.get("/orga/admin/")
    request.user = user

    result = system_information(request)

    assert result["warning_update_available"] is False
    assert result["warning_update_check_active"] is False
