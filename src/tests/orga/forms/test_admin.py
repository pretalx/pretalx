# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.models.settings import GlobalSettings
from pretalx.orga.forms.admin import UpdateSettingsForm

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({"update_check_enabled": True, "update_check_email": "admin@example.com"}, {}),
        ({}, {}),
        (
            {"update_check_enabled": True, "update_check_email": "not-an-email"},
            {"update_check_email": ["Enter a valid email address."]},
        ),
    ),
    ids=["both", "empty", "invalid-email"],
)
def test_update_settings_form_clean(data, errors):
    form = UpdateSettingsForm(data=data)

    assert form.is_valid() == (not errors)
    assert form.errors == errors


def test_update_settings_form_save_enables_then_disables_check():
    gs = GlobalSettings()

    form = UpdateSettingsForm(
        data={"update_check_enabled": True, "update_check_email": "admin@example.com"}
    )
    assert form.is_valid(), form.errors
    form.save()
    gs.settings.flush()

    assert gs.settings.update_check_enabled is True
    assert gs.settings.update_check_email == "admin@example.com"

    form = UpdateSettingsForm(data={"update_check_email": ""})
    assert form.is_valid(), form.errors
    form.save()
    gs.settings.flush()

    assert gs.settings.update_check_enabled is False
    assert gs.settings.update_check_email == ""
