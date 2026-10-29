# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.cache import cache

from pretalx.common.signals import (
    EventPluginSignal,
    _populate_app_cache,
    app_cache,
    minimum_interval,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit]


def _make_receiver(module):
    def receiver(
        signal=None, sender=None, **kwargs
    ):  # pragma: no cover – stub for _is_active() checks, never dispatched
        pass

    receiver.__module__ = module
    return receiver


def _make_handler():
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
    settings.CORE_MODULES = []
    _populate_app_cache()
    receiver = _make_receiver("tests.dummy_app.views")
    event = EventFactory(plugins=plugins)

    assert EventPluginSignal._is_active(event, receiver) is expected


def test_event_plugin_signal_is_active_no_sender(settings):
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
def test_event_plugin_signal_send_calls_active_receivers_sorted_by_name(
    register_signal_handler,
):
    signal = EventPluginSignal()
    event = EventFactory()
    handler_b = _make_handler()
    handler_b.__name__ = "handler_b"
    handler_a = _make_handler()
    handler_a.__name__ = "handler_a"

    register_signal_handler(signal, handler_b)
    register_signal_handler(signal, handler_a)
    app_cache.clear()
    responses = signal.send(event)

    assert responses == [(handler_a, "ok"), (handler_b, "ok")]
    assert handler_a.received == [event]
    assert handler_b.received == [event]
    assert "pretalx.common" in app_cache


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
    app_cache.clear()
    responses = signal.send_robust(event)

    assert [(r[0], str(r[1]), type(r[1])) for r in responses] == [
        (bad_handler, "fail", RuntimeError),
        (good_handler, "ok", str),
    ]
    assert "pretalx.common" in app_cache


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
    app_cache.clear()
    result = signal.send_chained(event, chain_kwarg_name="value", value="hello")

    assert result == "hello!?"
    assert "pretalx.common" in app_cache


def test_event_plugin_signal_get_live_receivers_empty():
    signal = EventPluginSignal()

    result = signal.get_live_receivers(None)

    assert result == []


def test_minimum_interval_blocks_second_call_and_releases_lock():
    calls = []

    @minimum_interval(minutes_after_success=10, minutes_running_timeout=30)
    def task():
        calls.append(1)
        return "done"

    key_running = (
        f"pretalx_periodic_{task.__module__}.{task.__wrapped__.__name__}_running"
    )

    assert task() == "done"
    assert cache.get(key_running) is None
    assert task() is None
    assert calls == [1]


def test_minimum_interval_blocks_during_running():
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


def test_minimum_interval_caches_error_result_and_releases_lock():
    calls = []

    @minimum_interval(
        minutes_after_success=10, minutes_after_error=5, minutes_running_timeout=30
    )
    def task():
        calls.append(1)
        raise RuntimeError("fail")

    key_running = (
        f"pretalx_periodic_{task.__module__}.{task.__wrapped__.__name__}_running"
    )

    with pytest.raises(RuntimeError, match="fail"):
        task()

    assert cache.get(key_running) is None
    assert task() is None
    assert calls == [1]
