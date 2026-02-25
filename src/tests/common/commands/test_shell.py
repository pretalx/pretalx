import logging
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection

from pretalx.common.management.commands.shell import Command

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_shell_handle_no_event_or_scopes_exits():
    with pytest.raises(SystemExit):
        call_command("shell", command="pass")


@pytest.mark.django_db
def test_shell_handle_event_not_found_exits():
    with pytest.raises(SystemExit):
        call_command("shell", event="nonexistent-slug-xyz", command="pass")


@pytest.mark.django_db
def test_shell_handle_unsafe_disable_scopes_runs_command():
    call_command("shell", unsafe_disable_scopes=True, command="pass")


@pytest.mark.django_db
def test_shell_handle_print_sql_enables_debug_cursor(event):
    original = connection.force_debug_cursor
    try:
        call_command(
            "shell", print_sql=True, event=event.slug, no_startup=True, command="pass"
        )

        assert connection.force_debug_cursor is True
    finally:
        connection.force_debug_cursor = original


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("extra_kwargs", "expected_prefix"),
    (({}, "In [0]: event"), ({"interface": "python"}, ">>> event")),
    ids=("ipython_style", "python_style"),
)
def test_shell_handle_with_event_prints_event_info(
    event, extra_kwargs, expected_prefix
):
    """IPython-style info is printed by default (IPython is installed in the
    test env); forcing 'python' interface uses plain Python-style instead."""
    out = StringIO()

    call_command(
        "shell",
        event=event.slug,
        command="pass",
        stdout=out,
        no_color=True,
        **extra_kwargs,
    )
    output = out.getvalue()

    assert expected_prefix in output
    assert repr(event) in output


def test_shell_ipython_method_configures_ipython():
    """Mocking start_ipython: starts interactive terminal session (system boundary)."""
    cmd = Command()
    options = {"no_startup": True, "verbosity": 1, "no_imports": False}

    with patch("IPython.start_ipython") as mock_start:
        cmd.ipython(options)

    _, kwargs = mock_start.call_args
    assert kwargs["argv"] == []
    config = kwargs["config"]
    assert config.TerminalIPythonApp.display_banner is False
    assert config.TerminalInteractiveShell.enable_tip is False
