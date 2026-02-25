import pytest
from django.core.management import call_command
from django.db import models
from django.db.migrations.operations import models as modelops

from pretalx.common.management.commands.makemigrations import hack_model_fields

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_hack_state():
    """Save and restore global state that hack_model_fields modifies."""
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
    ("field", "stripped_attr"),
    (
        (models.CharField(max_length=100, verbose_name="My field"), "verbose_name"),
        (models.IntegerField(help_text="A helpful text"), "help_text"),
        (models.CharField(max_length=10, choices=[("a", "A"), ("b", "B")]), "choices"),
    ),
    ids=("verbose_name", "help_text", "choices"),
)
def test_hack_model_fields_strips_attr_from_field_deconstruct(field, stripped_attr):
    hack_model_fields()

    _, _, _, kwargs = field.deconstruct()

    assert stripped_attr not in kwargs


def test_hack_model_fields_preserves_blank_on_date_field():
    """DateField is in the blank blacklist, so blank should NOT be stripped."""
    hack_model_fields()
    field = models.DateField(blank=True)

    _, _, _, kwargs = field.deconstruct()

    assert "blank" in kwargs


def test_hack_model_fields_preserves_max_length_on_char_field():
    """max_length is not in the ignored attrs, so it must survive deconstruct."""
    hack_model_fields()
    field = models.CharField(max_length=255)

    _, _, _, kwargs = field.deconstruct()

    assert kwargs["max_length"] == 255


@pytest.mark.django_db
def test_makemigrations_check_finds_no_pending_changes():
    call_command("makemigrations", dry_run=True, check=True)
