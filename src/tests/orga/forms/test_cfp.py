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


@pytest.mark.parametrize(
    ("email", "help_text_suffix"),
    (
        ("", ""),
        (
            "test@example.com",
            ' (<a href="mailto:test@example.com">test@example.com</a>)',
        ),
        (
            '"><script>alert()</script>"@example.com',
            (
                ' (<a href="mailto:&quot;&gt;&lt;script&gt;alert()&lt;/script&gt;&quot;@example.com">'
                "&quot;&gt;&lt;script&gt;alert()&lt;/script&gt;&quot;@example.com</a>)"
            ),
        ),
    ),
    ids=["no-email", "email", "escaped-email"],
)
def test_cfp_settings_form_init(email, help_text_suffix):
    event = EventFactory(
        email=email,
        mail_settings={"mail_on_new_submission": True},
        feature_flags={"submission_public_review": True},
    )

    form = CfPSettingsForm(obj=event)

    assert form.fields["mail_on_new_submission"].initial is True
    assert form.fields["submission_public_review"].initial is True
    assert str(form.fields["mail_on_new_submission"].help_text) == (
        "If this setting is checked, you will receive an email to the organiser "
        "address for every received proposal." + help_text_suffix
    )


def test_cfp_settings_form_save_updates_json_fields_unless_read_only():
    event = EventFactory()
    data = {
        "mail_on_new_submission": True,
        "submission_public_review": False,
        "speakers_can_edit_submissions": True,
    }

    assert not CfPSettingsForm(data=data, obj=event, read_only=True).is_valid()

    form = CfPSettingsForm(data=data, obj=event)
    assert form.is_valid(), form.errors
    form.save()
    event.refresh_from_db()

    assert event.feature_flags["submission_public_review"] is False
    assert event.mail_settings["mail_on_new_submission"] is True
    assert event.feature_flags["speakers_can_edit_submissions"] is True


def test_cfp_form_saves_json_fields():
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
    ("field_key", "config", "count_length_in", "expected_valid"),
    (
        ("title", {"max_length": 5000}, "chars", False),
        ("title", {"min_length": 5000}, "chars", False),
        ("title", {"max_length": 1000}, "chars", True),
        ("title", {"max_length": 5000}, "words", True),
        ("abstract", {"max_length": 5000}, "chars", True),
        ("name", {"max_length": 5000}, "chars", True),
    ),
    ids=[
        "title-max-too-long",
        "title-min-too-long",
        "title-within-limit",
        "title-words",
        "abstract-unlimited",
        "field-without-length",
    ],
)
def test_cfp_form_count_length_in_rejects_lengths_above_model_limit(
    field_key, config, count_length_in, expected_valid
):
    event = EventFactory(
        cfp__settings={"count_length_in": "words"},
        cfp__fields={field_key: {"visibility": "optional", **config}},
    )
    cfp = event.cfp

    form = CfPForm(
        data={"headline_0": "Submit", "count_length_in": count_length_in},
        instance=cfp,
        locales=event.locales,
        event=event,
    )
    valid = form.is_valid()

    assert valid is expected_valid
    if not valid:
        assert list(form.errors) == ["count_length_in"]
        assert "5000" in str(form.errors["count_length_in"])
        assert "1000" in str(form.errors["count_length_in"])


@pytest.mark.parametrize(
    ("field_key", "extra_fields"),
    (
        ("title", ["min_length", "max_length"]),
        ("abstract", ["min_length", "max_length"]),
        ("description", ["min_length", "max_length"]),
        ("biography", ["min_length", "max_length"]),
        ("notes", []),
        ("image", []),
        ("additional_speaker", ["max"]),
        ("tags", ["min_number", "max_number"]),
    ),
)
def test_cfp_field_config_form_fields_per_field_key(field_key, extra_fields):
    event = EventFactory()

    form = CfPFieldConfigForm(field_key=field_key, event=event)

    assert list(form.fields) == ["label", "help_text", "visibility", *extra_fields]


def test_cfp_field_config_form_tags_help_text_mentions_public_tags():
    event = EventFactory()

    form = CfPFieldConfigForm(field_key="tags", event=event)

    assert str(form.fields["help_text"].help_text) == (
        "Additional instructions shown below the field. "
        "Note: Only public tags will be shown to submitters."
    )


@pytest.mark.parametrize(
    ("field_key", "data", "errors"),
    (
        (
            "tags",
            {"min_number": 5, "max_number": 2},
            {"__all__": ["Minimum tags cannot be greater than maximum tags."]},
        ),
        ("tags", {"min_number": 1, "max_number": 5}, {}),
        (
            "title",
            {"min_length": 10, "max_length": 5},
            {"__all__": ["Minimum length cannot be greater than maximum length."]},
        ),
        ("title", {"min_length": 5, "max_length": 10}, {}),
        ("title", {"min_length": 5, "max_length": 5}, {}),
        ("title", {"min_length": 10}, {}),
    ),
    ids=[
        "tags-min-above-max",
        "tags-valid",
        "min-above-max",
        "min-below-max",
        "min-equals-max",
        "min-only",
    ],
)
def test_cfp_field_config_form_clean_min_max(field_key, data, errors):
    event = EventFactory()

    form = CfPFieldConfigForm(
        data={"visibility": "optional", **data}, field_key=field_key, event=event
    )

    assert form.is_valid() == (not errors)
    assert form.errors == errors


@pytest.mark.parametrize("length_field", ("min_length", "max_length"))
@pytest.mark.parametrize(
    ("field_key", "length", "count_in", "expected_valid"),
    (
        ("title", 1000, "chars", True),
        ("title", 1001, "chars", False),
        ("title", 1001, "words", True),
        ("abstract", 100_000, "chars", True),
    ),
    ids=["title-at-limit", "title-above-limit", "title-words", "abstract-unlimited"],
)
def test_cfp_field_config_form_length_against_model_limit(
    length_field, field_key, length, count_in, expected_valid
):
    event = EventFactory(cfp__settings={"count_length_in": count_in})

    form = CfPFieldConfigForm(
        data={"visibility": "optional", length_field: length},
        field_key=field_key,
        event=event,
    )
    valid = form.is_valid()

    assert valid is expected_valid
    if not valid:
        assert form.errors == {
            length_field: ["This field cannot be longer than 1000 characters."]
        }


def test_step_header_form_valid_with_empty_data():
    event = EventFactory()

    form = StepHeaderForm(data={}, event=event)

    assert form.is_valid(), form.errors
