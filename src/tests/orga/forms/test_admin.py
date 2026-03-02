# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.models.settings import GlobalSettings
from pretalx.orga.forms.admin import GlobalSettingsForm, UpdateSettingsForm

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_global_settings_form_creates_global_settings_obj():
    form = GlobalSettingsForm()
    assert isinstance(form.obj, GlobalSettings)


def test_update_settings_form_valid_with_both_fields():
    form = UpdateSettingsForm(
        data={"update_check_enabled": True, "update_check_email": "admin@example.com"}
    )
    assert form.is_valid(), form.errors


def test_update_settings_form_valid_without_optional_fields():
    form = UpdateSettingsForm(data={})
    assert form.is_valid(), form.errors


def test_update_settings_form_invalid_email():
    form = UpdateSettingsForm(
        data={"update_check_enabled": True, "update_check_email": "not-an-email"}
    )
    assert not form.is_valid()
    assert "update_check_email" in form.errors


def test_update_settings_form_save_persists_values():
    form = UpdateSettingsForm(
        data={"update_check_enabled": True, "update_check_email": "admin@example.com"}
    )
    assert form.is_valid(), form.errors
    form.save()

    gs = GlobalSettings()
    gs.settings.flush()
    assert gs.settings.update_check_enabled is True
    assert gs.settings.update_check_email == "admin@example.com"


def test_update_settings_form_save_disables_check():
    # First enable it
    gs = GlobalSettings()
    gs.settings.update_check_enabled = True
    gs.settings.update_check_email = "old@example.com"

    form = UpdateSettingsForm(data={"update_check_email": ""})
    assert form.is_valid(), form.errors
    form.save()

    gs.settings.flush()
    assert gs.settings.update_check_enabled is False
    assert gs.settings.update_check_email == ""


@pytest.mark.parametrize("field", ("update_check_enabled", "update_check_email"))
def test_update_settings_form_field_not_required(field):
    form = UpdateSettingsForm()
    assert form.fields[field].required is False
