# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.management import call_command
from django.db import models
from django.db.migrations.operations import models as modelops

from pretalx.common.management.commands.makemigrations import hack_model_fields

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_hack_state():
    original_keys = list(modelops.AlterModelOptions.ALTER_OPTION_KEYS)
    original_deconstruct = models.Field.deconstruct
    yield
    modelops.AlterModelOptions.ALTER_OPTION_KEYS = original_keys
    models.Field.deconstruct = original_deconstruct


def test_hack_model_fields_removes_alter_option_keys():
    removed = {
        "verbose_name",
        "verbose_name_plural",
        "ordering",
        "get_latest_by",
        "default_manager_name",
        "permissions",
        "default_permissions",
    }

    hack_model_fields()

    for key in removed:
        assert key not in modelops.AlterModelOptions.ALTER_OPTION_KEYS


@pytest.mark.parametrize(
    ("field", "expected_kwargs"),
    (
        (
            models.CharField(max_length=100, verbose_name="My field"),
            {"max_length": 100},
        ),
        (models.IntegerField(help_text="A helpful text"), {}),
        (
            models.CharField(max_length=10, choices=[("a", "A"), ("b", "B")]),
            {"max_length": 10},
        ),
        (models.DateField(blank=True), {"blank": True}),
    ),
    ids=("verbose_name", "help_text", "choices", "blank_kept"),
)
def test_hack_model_fields_strips_display_attrs_from_field_deconstruct(
    field, expected_kwargs
):
    hack_model_fields()

    _, _, _, kwargs = field.deconstruct()

    assert kwargs == expected_kwargs


@pytest.mark.django_db
def test_makemigrations_check_finds_no_pending_changes():
    call_command("makemigrations", dry_run=True, check=True)
