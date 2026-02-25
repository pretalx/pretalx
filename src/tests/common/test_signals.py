import pytest
from django.core.cache import cache

from pretalx.common.signals import (
    EventPluginSignal,
    _populate_app_cache,
    app_cache,
    minimum_interval,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("locmem_cache")]


def _make_receiver(module):
    """Create a callable signal receiver with the given __module__."""

    def receiver(
        signal=None, sender=None, **kwargs
    ):  # pragma: no cover – stub for _is_active() checks, never dispatched
        pass

    receiver.__module__ = module
    return receiver


def _make_handler():
    """Return a signal handler that tracks calls via handler.received."""
    received = []

    def handler(signal, sender, **kwargs):
        received.append(sender)
        return "ok"

    handler.received = received
    return handler


def test_populate_app_cache_fills_cache():
    app_cache.clear()

    _populate_app_cache()

    assert "pretalx.common" in app_cache


@pytest.mark.django_db
def test_event_plugin_signal_is_active_core_module(settings):
    """Receivers from core modules are always active regardless of event plugins."""
    settings.CORE_MODULES = ["mycore.module"]
    _populate_app_cache()
    receiver = _make_receiver("mycore.module.submodule")
    event = EventFactory(plugins="")

    assert EventPluginSignal._is_active(event, receiver) is True


@pytest.mark.parametrize(
    ("plugins", "expected"),
    (("", False), ("some.other.plugin", False), ("tests.dummy_app", True)),
    ids=("empty_plugins", "other_plugin", "matching_plugin"),
)
@pytest.mark.django_db
def test_event_plugin_signal_is_active_non_core_receiver(plugins, expected, settings):
    """Non-core receivers are active only when their app is in the event's plugin list."""
    settings.CORE_MODULES = []
    _populate_app_cache()
    receiver = _make_receiver("tests.dummy_app.views")
    event = EventFactory(plugins=plugins)

    assert EventPluginSignal._is_active(event, receiver) is expected


def test_event_plugin_signal_is_active_no_sender(settings):
    """With sender=None, non-core receivers are inactive."""
    settings.CORE_MODULES = []
    receiver = _make_receiver("tests.dummy_app.views")

    assert EventPluginSignal._is_active(None, receiver) is False


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    (
        ("send", {}),
        ("send_robust", {}),
        ("send_chained", {"chain_kwarg_name": "value"}),
    ),
)
@pytest.mark.django_db
def test_event_plugin_signal_requires_event_instance(method_name, kwargs):
    signal = EventPluginSignal()

    with pytest.raises(ValueError, match="event"):
        getattr(signal, method_name)("not-an-event", **kwargs)


@pytest.mark.parametrize(
    ("method_name", "kwargs", "expected"),
    (
        ("send", {}, []),
        ("send_robust", {}, []),
        ("send_chained", {"chain_kwarg_name": "value", "value": "initial"}, "initial"),
    ),
)
@pytest.mark.django_db
def test_event_plugin_signal_no_receivers(method_name, kwargs, expected):
    signal = EventPluginSignal()
    event = EventFactory()

    result = getattr(signal, method_name)(event, **kwargs)

    assert result == expected


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    (
        ("send", {}),
        ("send_robust", {}),
        ("send_chained", {"chain_kwarg_name": "value", "value": "untouched"}),
    ),
)
@pytest.mark.django_db
def test_event_plugin_signal_skips_inactive_receivers(method_name, kwargs, settings):
    """Receivers not belonging to active plugins are not called."""
    signal = EventPluginSignal()
    settings.CORE_MODULES = []
    _populate_app_cache()
    handler = _make_handler()
    handler.__module__ = "nonexistent.plugin"
    signal.connect(handler)
    try:
        event = EventFactory(plugins="")
        getattr(signal, method_name)(event, **kwargs)

        assert handler.received == []
    finally:
        signal.disconnect(handler)


@pytest.mark.django_db
def test_event_plugin_signal_send_calls_active_receivers(register_signal_handler):
    signal = EventPluginSignal()
    event = EventFactory()
    handler = _make_handler()

    register_signal_handler(signal, handler)
    responses = signal.send(event)

    assert handler.received == [event]
    assert responses[0][1] == "ok"


@pytest.mark.django_db
def test_event_plugin_signal_send_populates_app_cache(register_signal_handler):
    """send() populates app_cache on demand if it's empty."""
    signal = EventPluginSignal()
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return "ok"

    register_signal_handler(signal, handler)
    app_cache.clear()
    responses = signal.send(event)

    assert len(app_cache) > 0
    assert responses[0][1] == "ok"


@pytest.mark.django_db
def test_event_plugin_signal_send_responses_sorted(register_signal_handler):
    """Responses are sorted by (module, name)."""
    signal = EventPluginSignal()
    event = EventFactory()

    def handler_b(signal, sender, **kwargs):
        return "b"

    def handler_a(signal, sender, **kwargs):
        return "a"

    register_signal_handler(signal, handler_b)
    register_signal_handler(signal, handler_a)
    responses = signal.send(event)

    names = [r[0].__name__ for r in responses]
    assert names == sorted(names)


@pytest.mark.django_db
def test_event_plugin_signal_send_robust_populates_app_cache(register_signal_handler):
    """send_robust() populates app_cache on demand if it's empty."""
    signal = EventPluginSignal()
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return "ok"

    register_signal_handler(signal, handler)
    app_cache.clear()
    responses = signal.send_robust(event)

    assert len(app_cache) > 0
    assert responses[0][1] == "ok"


@pytest.mark.django_db
def test_event_plugin_signal_send_robust_catches_exceptions(register_signal_handler):
    signal = EventPluginSignal()
    event = EventFactory()

    def bad_handler(signal, sender, **kwargs):
        raise RuntimeError("boom")

    register_signal_handler(signal, bad_handler)
    responses = signal.send_robust(event)

    assert len(responses) == 1
    assert isinstance(responses[0][1], RuntimeError)
    assert str(responses[0][1]) == "boom"


@pytest.mark.django_db
def test_event_plugin_signal_send_robust_returns_successful_and_failed(
    register_signal_handler,
):
    signal = EventPluginSignal()
    event = EventFactory()

    def good_handler(signal, sender, **kwargs):
        return "ok"

    def bad_handler(signal, sender, **kwargs):
        raise RuntimeError("fail")

    register_signal_handler(signal, good_handler)
    register_signal_handler(signal, bad_handler)
    responses = signal.send_robust(event)

    results = {r[0].__name__: r[1] for r in responses}
    assert results["good_handler"] == "ok"
    assert isinstance(results["bad_handler"], RuntimeError)


@pytest.mark.django_db
def test_event_plugin_signal_send_chained_populates_app_cache(register_signal_handler):
    """send_chained() populates app_cache on demand if it's empty."""
    signal = EventPluginSignal()
    event = EventFactory()

    def handler(signal, sender, value, **kwargs):
        return value + "!"

    register_signal_handler(signal, handler)
    app_cache.clear()
    result = signal.send_chained(event, chain_kwarg_name="value", value="hi")

    assert len(app_cache) > 0
    assert result == "hi!"


@pytest.mark.django_db
def test_event_plugin_signal_send_chained_passes_return_to_next(
    register_signal_handler,
):
    signal = EventPluginSignal()
    event = EventFactory()

    def handler_add_excl(signal, sender, value, **kwargs):
        return value + "!"

    def handler_add_q(signal, sender, value, **kwargs):
        return value + "?"

    register_signal_handler(signal, handler_add_excl)
    register_signal_handler(signal, handler_add_q)
    result = signal.send_chained(event, chain_kwarg_name="value", value="hello")

    assert result == "hello!?"


def test_event_plugin_signal_get_live_receivers_empty():
    signal = EventPluginSignal()

    result = signal.get_live_receivers(None)

    assert result == []


def test_minimum_interval_allows_first_call():
    calls = []

    @minimum_interval(minutes_after_success=10)
    def task():
        calls.append(1)
        return "done"

    result = task()

    assert calls == [1]
    assert result == "done"


def test_minimum_interval_blocks_second_call():
    calls = []

    @minimum_interval(minutes_after_success=10)
    def task():
        calls.append(1)
        return "done"

    task()
    task()

    assert calls == [1]


def test_minimum_interval_blocks_during_running():
    """While a task is 'running', duplicate calls are blocked."""
    calls = []

    @minimum_interval(minutes_after_success=10, minutes_running_timeout=30)
    def task():  # pragma: no cover – body intentionally unreachable; test asserts the running lock blocks execution
        calls.append(1)
        return "done"

    key_running = (
        f"pretalx_periodic_{task.__module__}.{task.__wrapped__.__name__}_running"
    )
    cache.set(key_running, "some-uuid", timeout=60)

    task()

    assert calls == []


def test_minimum_interval_caches_error_result():
    """After a failure, the task is blocked for minutes_after_error."""
    calls = []

    @minimum_interval(minutes_after_success=10, minutes_after_error=5)
    def task():
        calls.append(1)
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError, match="fail"):
        task()

    # Second call is blocked due to error cooldown
    task()

    assert calls == [1]


def test_minimum_interval_releases_lock_after_success():
    """The running lock is released after a successful run,
    and the result cache blocks subsequent calls."""

    @minimum_interval(minutes_after_success=10, minutes_running_timeout=30)
    def task():
        return "done"

    task()

    key_running = (
        f"pretalx_periodic_{task.__module__}.{task.__wrapped__.__name__}_running"
    )
    assert cache.get(key_running) is None


def test_minimum_interval_releases_lock_after_error():
    """The running lock is released even after a failed run."""

    @minimum_interval(minutes_after_success=10, minutes_running_timeout=30)
    def task():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        task()

    key_running = (
        f"pretalx_periodic_{task.__module__}.{task.__wrapped__.__name__}_running"
    )
    assert cache.get(key_running) is None
