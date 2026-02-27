import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.dispatch import Signal
from django.utils.module_loading import import_string

from pretalx.orga.context_processors import collect_signal, orga_events
from pretalx.orga.signals import html_head, nav_event, nav_event_settings, nav_global
from tests.factories import EventFactory, UserFactory
from tests.utils import SimpleSession, make_orga_user, make_request

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")

pytestmark = pytest.mark.unit


def test_collect_signal_returns_list_responses():
    """collect_signal flattens list responses from signal receivers."""
    signal = Signal()
    items = [{"label": "A"}, {"label": "B"}]

    def handler(signal, sender, **kwargs):
        return items

    signal.connect(handler)
    try:
        result = collect_signal(signal, {"sender": None})
        assert result == items
    finally:
        signal.disconnect(handler)


def test_collect_signal_returns_scalar_responses():
    signal = Signal()

    def handler(signal, sender, **kwargs):
        return {"label": "Single"}

    signal.connect(handler)
    try:
        result = collect_signal(signal, {"sender": None})
        assert result == [{"label": "Single"}]
    finally:
        signal.disconnect(handler)


def test_collect_signal_filters_exceptions_from_list():
    """Exceptions inside list responses are filtered out."""
    signal = Signal()

    def handler(signal, sender, **kwargs):
        return [{"label": "Good"}, ValueError("bad")]

    signal.connect(handler)
    try:
        result = collect_signal(signal, {"sender": None})
        assert result == [{"label": "Good"}]
    finally:
        signal.disconnect(handler)


def test_collect_signal_filters_exception_responses():
    """If a receiver raises an exception, send_robust catches it and
    collect_signal skips it."""
    signal = Signal()

    def handler(signal, sender, **kwargs):
        raise RuntimeError("boom")

    signal.connect(handler)
    try:
        result = collect_signal(signal, {"sender": None})
        assert result == []
    finally:
        signal.disconnect(handler)


def test_collect_signal_empty_when_no_receivers():
    signal = Signal()
    result = collect_signal(signal, {"sender": None})
    assert result == []


def test_orga_events_returns_empty_for_non_orga_path():
    """Requests not starting with /orga/ get an empty context."""
    request = make_request(event=None, path="/agenda/talk/")
    result = orga_events(request)
    assert result == {}


def test_orga_events_returns_settings_for_unauthenticated_user():
    """Unauthenticated users on /orga/ paths get only Django settings in context."""
    request = make_request(event=None, path="/orga/login/")
    request.user = AnonymousUser()
    result = orga_events(request)
    assert result == {"settings": settings}


def test_orga_events_returns_settings_for_no_user_attr():
    """If request has no user attribute at all, return just settings."""
    request = make_request(event=None, path="/orga/login/")
    del request.user
    result = orga_events(request)
    assert result == {"settings": settings}


@pytest.mark.django_db
def test_orga_events_returns_nav_global_without_event(register_signal_handler):
    """Authenticated user on /orga/ without event gets nav_global entries."""
    user = UserFactory()
    request = make_request(event=None, path="/orga/")
    request.user = user
    del request.event

    entry = {"label": "Global Nav", "url": "/orga/admin/"}

    def handler(signal, sender, **kwargs):
        return [entry]

    register_signal_handler(nav_global, handler)
    result = orga_events(request)

    assert result["settings"] is settings
    assert result["nav_global"] == [entry]


@pytest.mark.django_db
def test_orga_events_nav_global_filters_falsy_entries(register_signal_handler):
    """Falsy entries (None, empty strings) from nav_global are filtered out."""
    user = UserFactory()
    request = make_request(event=None, path="/orga/")
    request.user = user
    del request.event

    real_entry = {"label": "Real", "url": "/orga/"}

    def handler(signal, sender, **kwargs):
        return [None, real_entry, ""]

    register_signal_handler(nav_global, handler)
    result = orga_events(request)
    assert result["nav_global"] == [real_entry]


@pytest.mark.django_db
def test_orga_events_with_event_returns_nav_and_pagination():
    """Authenticated user with event gets nav_event, nav_settings, html_head, and pagination."""
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    result = orga_events(request)

    assert result["settings"] is settings
    assert result["nav_event"] == []
    assert result["nav_settings"] == []
    assert result["nav_settings_expanded"] is False
    assert result["html_head"] == ""
    assert result["pagination_sizes"] == [50, 100, 250]


@pytest.mark.django_db
def test_orga_events_nav_event_collects_list_responses(register_signal_handler):
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()
    entry = {"label": "Plugin Nav", "url": "/orga/event/test/plugin/"}

    def handler(signal, sender, **kwargs):
        return [entry]

    register_signal_handler(nav_event, handler)
    result = orga_events(request)
    assert result["nav_event"] == [entry]


@pytest.mark.django_db
def test_orga_events_nav_event_ignores_non_list_responses(register_signal_handler):
    """nav_event only collects list responses; scalar responses are ignored."""
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    def handler(signal, sender, **kwargs):
        return {"label": "Scalar"}

    register_signal_handler(nav_event, handler)
    result = orga_events(request)
    assert result["nav_event"] == []


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
    assert result["nav_settings_expanded"] is expected


@pytest.mark.django_db
def test_orga_events_html_head_concatenates_strings(register_signal_handler):
    event = EventFactory()
    user = UserFactory()
    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    def handler1(signal, sender, **kwargs):
        return "<link>"

    def handler2(signal, sender, **kwargs):
        return "<script>"

    register_signal_handler(html_head, handler1)
    register_signal_handler(html_head, handler2)
    result = orga_events(request)
    assert result["html_head"] == "<link><script>"


@pytest.mark.django_db
def test_orga_events_creates_child_session_for_non_public_custom_domain():
    """When event is non-public with a custom domain and user has view_event
    permission, a child session is created and persisted in the store."""
    event = EventFactory(is_public=False, custom_domain="https://custom.example.com")
    user = make_orga_user(event)

    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()
    request.session.session_key = "parent-session-key"

    result = orga_events(request)

    child_session_key = f"child_session_{event.pk}"
    new_session_key = result["new_session"]
    assert request.session[child_session_key] == new_session_key
    assert request.session["event_access"] is True
    assert SessionStore().exists(new_session_key)


@pytest.mark.django_db
def test_orga_events_reuses_existing_child_session():
    """When a child session already exists and is still valid, it is reused."""
    event = EventFactory(is_public=False, custom_domain="https://custom.example.com")
    user = make_orga_user(event)

    store = SessionStore()
    store.create()
    existing_key = store.session_key

    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()
    request.session.session_key = "parent-session-key"
    request.session[f"child_session_{event.pk}"] = existing_key

    result = orga_events(request)

    assert result["new_session"] == existing_key
    assert request.session["event_access"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "custom_domain"),
    (
        pytest.param(True, "https://custom.example.com", id="public_event"),
        pytest.param(False, "", id="no_custom_domain"),
    ),
)
def test_orga_events_no_child_session(is_public, custom_domain):
    event = EventFactory(is_public=is_public, custom_domain=custom_domain)
    user = make_orga_user(event)

    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    result = orga_events(request)

    assert "new_session" not in result


@pytest.mark.django_db
def test_orga_events_no_child_session_without_view_permission():
    """Non-public event with custom domain but user lacks view_event permission
    does not create a child session."""
    event = EventFactory(is_public=False, custom_domain="https://custom.example.com")
    user = UserFactory()

    request = make_request(event, user=user, path="/orga/event/test/")
    request.session = SimpleSession()

    result = orga_events(request)

    assert "new_session" not in result
