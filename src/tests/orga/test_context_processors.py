# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.dispatch import Signal
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe

from pretalx.orga.context_processors import collect_signal, orga_events
from pretalx.orga.signals import html_head, nav_event, nav_event_settings, nav_global
from tests.factories import EventFactory, UserFactory
from tests.utils import SimpleSession, make_orga_user, make_request

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("response", "expected"),
    (
        ([{"label": "A"}, {"label": "B"}], [{"label": "A"}, {"label": "B"}]),
        ({"label": "Single"}, [{"label": "Single"}]),
        ([{"label": "Good"}, ValueError("bad")], [{"label": "Good"}]),
    ),
    ids=("list", "scalar", "list-with-exception"),
)
def test_collect_signal_collects_responses(response, expected):
    signal = Signal()

    def handler(signal, sender, **kwargs):
        return response

    signal.connect(handler)
    try:
        assert collect_signal(signal, {"sender": None}) == expected
    finally:
        signal.disconnect(handler)


def test_collect_signal_drops_raising_handlers():
    signal = Signal()

    assert collect_signal(signal, {"sender": None}) == []

    def handler(signal, sender, **kwargs):
        raise RuntimeError("boom")

    signal.connect(handler)
    try:
        assert collect_signal(signal, {"sender": None}) == []
    finally:
        signal.disconnect(handler)


def test_orga_events_outside_orga_or_unauthenticated():
    non_orga = make_request(event=None, path="/agenda/talk/")
    anonymous = make_request(event=None, path="/orga/login/")
    anonymous.user = AnonymousUser()
    no_user = make_request(event=None, path="/orga/login/")
    del no_user.user

    assert orga_events(non_orga) == {}
    assert orga_events(anonymous) == {"settings": settings}
    assert orga_events(no_user) == {"settings": settings}


@pytest.mark.django_db
def test_orga_events_returns_nav_global_without_event(register_signal_handler):
    user = UserFactory()
    request = make_request(event=None, path="/orga/")
    request.user = user
    del request.event
    entry = {"label": "Global Nav", "url": "/orga/admin/"}

    def handler(signal, sender, **kwargs):
        return [None, entry, ""]

    register_signal_handler(nav_global, handler)
    result = orga_events(request)

    assert result == {"settings": settings, "nav_global": [entry]}


@pytest.mark.django_db
def test_orga_events_with_event_collects_nav_and_html_head(register_signal_handler):
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    assert orga_events(request) == {
        "settings": settings,
        "nav_event": [],
        "nav_settings": [],
        "nav_settings_expanded": False,
        "html_head": "",
        "pagination_sizes": [50, 100, 250],
    }

    entry = {"label": "Plugin Nav", "url": "/orga/event/test/plugin/"}
    register_signal_handler(nav_event, lambda signal, sender, **kwargs: [entry])
    register_signal_handler(
        nav_event, lambda signal, sender, **kwargs: {"label": "Scalar"}
    )
    register_signal_handler(
        html_head, lambda signal, sender, **kwargs: mark_safe("<link>")
    )
    register_signal_handler(
        html_head, lambda signal, sender, **kwargs: "<script>alert(1)</script>"
    )
    register_signal_handler(html_head, lambda signal, sender, **kwargs: None)
    result = orga_events(request)

    assert result["nav_event"] == [entry]
    assert result["html_head"] == "<link>&lt;script&gt;alert(1)&lt;/script&gt;"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("request_path", "entry_url", "expected"),
    (
        pytest.param(
            "/orga/event/test/settings/plugin/",
            "/orga/event/test/settings/plugin/",
            True,
            id="matching_path",
        ),
        pytest.param(
            "/orga/event/test/settings/general/",
            "/orga/event/test/settings/plugin/",
            False,
            id="different_path",
        ),
    ),
)
def test_orga_events_nav_settings_expanded(
    register_signal_handler, request_path, entry_url, expected
):
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path=request_path)
    request.session = SimpleSession()

    entry = {"label": "Plugin Settings", "url": entry_url}

    def handler(signal, sender, **kwargs):
        return entry

    register_signal_handler(nav_event_settings, handler)
    result = orga_events(request)
    assert result["nav_settings"] == [entry]
    assert result["nav_settings_expanded"] is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "team_kwargs"),
    (
        pytest.param(False, {}, id="private-organiser"),
        pytest.param(
            True,
            {"can_change_submissions": False, "is_reviewer": True},
            id="public-reviewer",
        ),
    ),
)
def test_orga_events_creates_and_reuses_child_session_for_custom_domain(
    is_public, team_kwargs
):
    event = EventFactory(
        is_public=is_public, custom_domain="https://custom.example.com"
    )
    user = make_orga_user(event, all_events=True, **team_kwargs)
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()
    request.session.session_key = "parent-session-key"

    new_session_key = orga_events(request)["new_session"]

    assert request.session[f"child_session_{event.pk}"] == new_session_key
    store = SessionStore(session_key=new_session_key)
    assert store.exists(new_session_key)
    assert store[f"pretalx_event_access_{event.pk}"] == "parent-session-key"
    assert orga_events(request)["new_session"] == new_session_key


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "custom_domain", "make_user"),
    (
        pytest.param(False, "", make_orga_user, id="no-custom-domain"),
        pytest.param(
            False,
            "https://custom.example.com",
            lambda event: UserFactory(),
            id="private-without-permission",
        ),
        pytest.param(
            True,
            "https://custom.example.com",
            lambda event: UserFactory(),
            id="public-without-permission",
        ),
    ),
)
def test_orga_events_no_child_session(is_public, custom_domain, make_user):
    event = EventFactory(is_public=is_public, custom_domain=custom_domain)
    request = make_request(event, user=make_user(event), path="/orga/event/test/")
    request.session = SimpleSession()

    assert "new_session" not in orga_events(request)
