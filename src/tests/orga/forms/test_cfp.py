# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.forms.cfp import (
    CfPFieldConfigForm,
    CfPForm,
    CfPSettingsForm,
    StepHeaderForm,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_cfp_settings_form_init_populates_json_fields():
    event = EventFactory(
        mail_settings={"mail_on_new_submission": True},
        feature_flags={"submission_public_review": True},
    )

    form = CfPSettingsForm(obj=event)

    assert form.fields["mail_on_new_submission"].initial is True
    assert form.fields["submission_public_review"].initial is True


def test_cfp_settings_form_init_appends_email_to_help_text():
    event = EventFactory(email="test@example.com")

    form = CfPSettingsForm(obj=event)

    assert "test@example.com" in form.fields["mail_on_new_submission"].help_text


def test_cfp_settings_form_init_no_email_skips_mailto():
    event = EventFactory(email="")

    form = CfPSettingsForm(obj=event)

    assert "mailto:" not in str(form.fields["mail_on_new_submission"].help_text)


def test_cfp_settings_form_save_updates_json_fields():
    event = EventFactory()

    form = CfPSettingsForm(
        data={
            "mail_on_new_submission": True,
            "submission_public_review": False,
            "speakers_can_edit_submissions": True,
        },
        obj=event,
    )
    assert form.is_valid(), form.errors
    form.save()
    event.refresh_from_db()

    assert event.feature_flags["submission_public_review"] is False
    assert event.mail_settings["mail_on_new_submission"] is True
    assert event.feature_flags["speakers_can_edit_submissions"] is True


def test_cfp_settings_form_read_only_rejects_changes():
    event = EventFactory()

    form = CfPSettingsForm(
        data={
            "mail_on_new_submission": False,
            "submission_public_review": False,
            "speakers_can_edit_submissions": True,
        },
        obj=event,
        read_only=True,
    )

    assert not form.is_valid()


def test_cfp_form_valid_with_minimal_data():
    event = EventFactory()
    cfp = event.cfp

    form = CfPForm(
        data={
            "headline_0": "Submit your talk!",
            "text_0": "We want your talks.",
            "count_length_in": "chars",
        },
        instance=cfp,
        locales=event.locales,
        event=event,
    )

    assert form.is_valid(), form.errors


def test_cfp_form_saves_json_fields():
    """show_deadline and count_length_in are stored in cfp.settings."""
    event = EventFactory()
    cfp = event.cfp

    form = CfPForm(
        data={
            "headline_0": "Submit",
            "text_0": "",
            "show_deadline": True,
            "count_length_in": "words",
        },
        instance=cfp,
        locales=event.locales,
        event=event,
    )
    assert form.is_valid(), form.errors
    form.save()
    cfp.refresh_from_db()

    assert cfp.settings["show_deadline"] is True
    assert cfp.settings["count_length_in"] == "words"


@pytest.mark.parametrize(
    ("field_key", "expect_length_fields"),
    (
        ("title", True),
        ("abstract", True),
        ("description", True),
        ("biography", True),
        ("notes", False),
        ("image", False),
    ),
    ids=["title", "abstract", "description", "biography", "notes", "image"],
)
def test_cfp_field_config_form_length_fields_presence(field_key, expect_length_fields):
    """min_length/max_length fields are only present for text-like fields."""
    event = EventFactory()

    form = CfPFieldConfigForm(field_key=field_key, event=event)

    assert ("min_length" in form.fields) is expect_length_fields
    assert ("max_length" in form.fields) is expect_length_fields


def test_cfp_field_config_form_max_speakers_only_for_additional_speaker():
    event = EventFactory()

    form_speaker = CfPFieldConfigForm(field_key="additional_speaker", event=event)
    form_other = CfPFieldConfigForm(field_key="title", event=event)

    assert "max" in form_speaker.fields
    assert "max" not in form_other.fields


def test_cfp_field_config_form_tag_fields_only_for_tags():
    event = EventFactory()

    form_tags = CfPFieldConfigForm(field_key="tags", event=event)
    form_other = CfPFieldConfigForm(field_key="title", event=event)

    assert "min_number" in form_tags.fields
    assert "max_number" in form_tags.fields
    assert "min_number" not in form_other.fields
    assert "max_number" not in form_other.fields


def test_cfp_field_config_form_tags_help_text_mentions_public_tags():
    event = EventFactory()

    form = CfPFieldConfigForm(field_key="tags", event=event)

    assert "public tags" in str(form.fields["help_text"].help_text).lower()


def test_cfp_field_config_form_clean_rejects_min_greater_than_max():
    event = EventFactory()

    form = CfPFieldConfigForm(
        data={"visibility": "optional", "min_number": 5, "max_number": 2},
        field_key="tags",
        event=event,
    )
    valid = form.is_valid()

    assert not valid


def test_cfp_field_config_form_clean_accepts_valid_tag_range():
    event = EventFactory()

    form = CfPFieldConfigForm(
        data={"visibility": "optional", "min_number": 1, "max_number": 5},
        field_key="tags",
        event=event,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_step_header_form_valid_with_empty_data():
    event = EventFactory()

    form = StepHeaderForm(data={}, event=event)

    assert form.is_valid(), form.errors


def test_step_header_form_sets_text_rows():
    event = EventFactory()

    form = StepHeaderForm(event=event)

    assert form.fields["text"].widget.attrs["rows"] == "3"
