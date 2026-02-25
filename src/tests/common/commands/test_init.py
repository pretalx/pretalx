import os
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from pretalx.common.management.commands.init import Command, prompt_nonempty
from pretalx.event.models import Organiser
from pretalx.person.models import User

pytestmark = pytest.mark.unit


def test_prompt_nonempty_returns_stripped_input():
    # Mocking builtins.input: requires interactive terminal (system boundary).
    with patch("builtins.input", return_value="  hello  "):
        result = prompt_nonempty("Enter: ")

    assert result == "hello"


def test_prompt_nonempty_retries_on_empty_input():
    # Mocking builtins.input: requires interactive terminal (system boundary).
    with patch("builtins.input", side_effect=["", "valid"]):
        result = prompt_nonempty("Enter: ")

    assert result == "valid"


def test_init_get_nonempty_interactive_returns_input():
    cmd = Command(stdout=StringIO())

    # Mocking builtins.input: requires interactive terminal (system boundary).
    with patch("builtins.input", return_value="interactive_value"):
        result = cmd.get_nonempty("Prompt: ")

    assert result == "interactive_value"


def test_init_get_nonempty_reads_env_var():
    cmd = Command(stdout=StringIO())

    with patch.dict(os.environ, {"MY_TEST_VAR": "env_value"}):
        result = cmd.get_nonempty("Prompt: ", "MY_TEST_VAR")

    assert result == "env_value"


def test_init_get_nonempty_raises_on_missing_env_var():
    cmd = Command(stdout=StringIO())

    with pytest.raises(ValueError, match="MY_TEST_VAR"):
        cmd.get_nonempty("Prompt: ", "MY_TEST_VAR")


@pytest.mark.django_db
def test_init_handle_interactive_propagates_keyboard_interrupt():
    # Mocking builtins.input: requires interactive terminal (system boundary).
    with (
        patch("builtins.input", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        call_command("init")


@pytest.mark.django_db
def test_init_handle_noinput_missing_env_var_exits():
    """Non-interactive mode exits when required env vars are missing."""
    env_overrides = {
        "DJANGO_SUPERUSER_EMAIL": "",
        "DJANGO_SUPERUSER_PASSWORD": "",
        "PRETALX_INIT_ORGANISER_NAME": "",
        "PRETALX_INIT_ORGANISER_SLUG": "",
    }

    with patch.dict(os.environ, env_overrides), pytest.raises(SystemExit):
        call_command("init", "--noinput")


@pytest.mark.django_db
def test_init_handle_noinput_creates_user_and_organiser():
    env = {
        "DJANGO_SUPERUSER_EMAIL": "admin@test-init.org",
        "DJANGO_SUPERUSER_PASSWORD": "testpass123!",
        "PRETALX_INIT_ORGANISER_NAME": "Test Org",
        "PRETALX_INIT_ORGANISER_SLUG": "testorg",
    }

    with patch.dict(os.environ, env):
        call_command("init", "--noinput")

    user = User.objects.get(email="admin@test-init.org")
    assert user.is_administrator is True
    organiser = Organiser.objects.get(slug="testorg")
    assert organiser.name == "Test Org"
    assert organiser.teams.first().members.filter(pk=user.pk).exists()
