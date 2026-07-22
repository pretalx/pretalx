# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import logging
import sys
from io import StringIO
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.db import connection

from pretalx.common.management.commands.shell import Command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_shell_handle_no_event_or_scopes_exits():
    with pytest.raises(SystemExit):
        call_command("shell", command="pass")


def test_shell_handle_event_not_found_exits():
    with pytest.raises(SystemExit):
        call_command("shell", event="nonexistent-slug-xyz", command="pass")


def test_shell_handle_unsafe_disable_scopes_runs_command():
    call_command("shell", unsafe_disable_scopes=True, command="pass")


def test_shell_handle_print_sql_enables_debug_cursor(event):
    original = connection.force_debug_cursor
    try:
        call_command(
            "shell", print_sql=True, event=event.slug, no_startup=True, command="pass"
        )

        assert connection.force_debug_cursor is True
    finally:
        connection.force_debug_cursor = original


def test_shell_handle_print_sql_adds_handler_when_logger_has_none(event):
    logger = logging.getLogger("django.db.backends")
    original_handlers = list(logger.handlers)
    original_cursor = connection.force_debug_cursor
    logger.handlers.clear()
    try:
        call_command(
            "shell", print_sql=True, event=event.slug, no_startup=True, command="pass"
        )

        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    finally:
        connection.force_debug_cursor = original_cursor
        logger.handlers = original_handlers


def test_shell_handle_no_startup_skips_event_info(event):
    out = StringIO()

    call_command(
        "shell",
        event=event.slug,
        no_startup=True,
        command="pass",
        stdout=out,
        no_color=True,
    )

    assert repr(event) not in out.getvalue()


def test_shell_handle_with_event_prints_ipython_style(event):
    """When IPython is importable, the default interface prints IPython-style
    prompts.  We inject a fake IPython module so the test works regardless
    of whether IPython is actually installed.  ``is_non_interactive`` is
    patched because we can't open a real interactive shell in tests."""
    out = StringIO()

    with (
        patch.dict(sys.modules, {"IPython": ModuleType("IPython")}),
        patch.object(Command, "is_non_interactive", return_value=False),
    ):
        call_command(
            "shell", event=event.slug, command="pass", stdout=out, no_color=True
        )
    output = out.getvalue()

    assert "In [0]: event" in output
    assert repr(event) in output


def test_shell_handle_with_event_prints_python_style(event):
    """Forcing 'python' interface uses plain Python-style prompts."""
    out = StringIO()

    with patch.object(Command, "is_non_interactive", return_value=False):
        call_command(
            "shell",
            event=event.slug,
            command="pass",
            stdout=out,
            no_color=True,
            interface="python",
        )
    output = out.getvalue()

    assert ">>> event" in output
    assert repr(event) in output


def test_shell_handle_command_produces_no_preamble(event):
    out = StringIO()

    call_command(
        "shell",
        event=event.slug,
        command="print(event.slug)",
        stdout=out,
        no_color=True,
    )

    assert out.getvalue() == ""


def test_shell_handle_command_suppresses_auto_import_banner(capsys):
    call_command("shell", unsafe_disable_scopes=True, command="print(Event)")

    assert capsys.readouterr().out == "<class 'pretalx.event.models.event.Event'>\n"


def test_shell_get_namespace_includes_scoped_event(event):
    command = Command()
    command.scoped_event = event

    assert command.get_namespace(verbosity=0)["event"] == event


def test_shell_get_namespace_without_scope_has_no_event():
    assert "event" not in Command().get_namespace(verbosity=0)


@pytest.mark.parametrize(
    ("options", "expected"),
    (({"command": "pass"}, True), ({"command": None}, False), ({}, False)),
)
def test_shell_is_non_interactive(options, expected):
    assert Command().is_non_interactive(options) is expected


def test_shell_is_non_interactive_with_tty():
    with patch.object(sys.stdin, "isatty", return_value=True):
        assert Command().is_non_interactive({}) is False


class _NestedNamespace:
    """Stand-in for traitlets.config.Config: auto-creates sub-namespaces."""

    def __getattr__(self, name):
        ns = _NestedNamespace()
        object.__setattr__(self, name, ns)
        return ns


def test_shell_ipython_method_configures_ipython():
    """Mocking start_ipython: starts interactive terminal session (system boundary)."""
    cmd = Command()
    options = {"no_startup": True, "verbosity": 1, "no_imports": False}
    mock_start = MagicMock()
    fake_ipython = ModuleType("IPython")
    fake_ipython.start_ipython = mock_start
    fake_traitlets_config = ModuleType("traitlets.config")
    fake_traitlets_config.Config = _NestedNamespace

    with patch.dict(
        sys.modules,
        {
            "IPython": fake_ipython,
            "traitlets": ModuleType("traitlets"),
            "traitlets.config": fake_traitlets_config,
        },
    ):
        cmd.ipython(options)

    _, kwargs = mock_start.call_args
    assert kwargs["argv"] == []
    config = kwargs["config"]
    assert config.TerminalIPythonApp.display_banner is False
    assert config.TerminalInteractiveShell.enable_tip is False
