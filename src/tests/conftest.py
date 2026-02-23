import pytest
from django_scopes import scopes_disabled

from tests.factories import EventFactory


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


@pytest.fixture
def register_signal_handler(settings):
    """Connect a temporary handler to an EventPluginSignal for the duration
    of a single test.

    Adds ``"tests._test_plugin"`` to ``CORE_MODULES`` and sets each
    handler's ``__module__`` to match, so handlers pass
    ``EventPluginSignal._is_active`` without needing a real plugin.
    The ``settings`` fixture auto-restores ``CORE_MODULES`` after the test;
    handlers are disconnected explicitly on teardown.

    Usage::

        def test_pre_send_hook(register_signal_handler, event):
            received = []

            def handler(signal, sender, **kwargs):
                received.append(kwargs["mail"])

            register_signal_handler(some_event_plugin_signal, handler)
            # … trigger the signal …
            assert len(received) == 1
    """
    registered = []
    settings.CORE_MODULES = [*settings.CORE_MODULES, "tests._test_plugin"]

    def _register(signal, handler):
        handler.__module__ = "tests._test_plugin"
        signal.connect(handler)
        registered.append((signal, handler))

    yield _register

    for signal, handler in registered:
        signal.disconnect(handler)
