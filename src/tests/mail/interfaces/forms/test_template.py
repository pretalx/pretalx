# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.mail.domain.placeholders import SimpleFunctionalMailTextPlaceholder
from pretalx.mail.interfaces.forms.template import MailTemplateForm
from pretalx.mail.signals import register_mail_placeholders
from tests.factories import EventFactory, MailTemplateFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_form_init_sets_required_fields():
    event = EventFactory()
    form = MailTemplateForm(event=event)

    assert form.fields["subject"].required is True
    assert form.fields["text"].required is True


def test_mail_template_form_init_uses_event_locales():
    event = EventFactory()
    form = MailTemplateForm(event=event)
    assert form.event == event


def test_mail_template_form_init_without_event():
    with pytest.raises(TypeError):
        MailTemplateForm()


def test_mail_template_form_init_with_none_event():
    with pytest.raises(TypeError):
        MailTemplateForm(event=None)


def test_mail_template_form_valid_data():
    event = EventFactory()
    form = MailTemplateForm(event=event, data={"subject_0": "Hello", "text_0": "World"})
    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("missing_field", "data"),
    (
        pytest.param("subject", {"subject_0": "", "text_0": "World"}, id="subject"),
        pytest.param("text", {"subject_0": "Hello", "text_0": ""}, id="text"),
    ),
)
def test_mail_template_form_clean_requires_field(missing_field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert missing_field in form.errors


def test_mail_template_form_clean_subject_valid_placeholder():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Hello {event_name}", "text_0": "Body text"}
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("field", "data"),
    (
        pytest.param(
            "subject",
            {"subject_0": "Hello {nonexistent_placeholder}", "text_0": "Body text"},
            id="subject",
        ),
        pytest.param(
            "text", {"subject_0": "Hello", "text_0": "Body {does_not_exist}"}, id="text"
        ),
    ),
)
def test_mail_template_form_clean_rejects_invalid_placeholder(field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.parametrize(
    ("field", "data"),
    (
        pytest.param(
            "subject",
            {"subject_0": "Hello { broken", "text_0": "Body text"},
            id="subject",
        ),
        pytest.param(
            "text", {"subject_0": "Hello", "text_0": "Body { broken"}, id="text"
        ),
    ),
)
def test_mail_template_form_clean_rejects_malformed_placeholder(field, data):
    event = EventFactory()
    form = MailTemplateForm(event=event, data=data)

    assert not form.is_valid()
    assert field in form.errors


def test_mail_template_form_clean_text_empty_link():
    # Empty-link rejection lives on MailTemplate.clean(); the modelform's
    # _post_clean path runs full_clean, so the error reaches form.errors["text"].
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Hello", "text_0": "[Click here]()"}
    )

    assert not form.is_valid()
    assert "text" in form.errors


def test_mail_template_form_clean_text_valid_link():
    event = EventFactory()
    form = MailTemplateForm(
        event=event,
        data={
            "subject_0": "Hello",
            "text_0": "Visit [our site](https://example.com) please",
        },
    )
    assert form.is_valid(), form.errors


def test_mail_template_form_get_valid_placeholders_sets_event():
    event = EventFactory()
    template = MailTemplateFactory(event=event)
    form = MailTemplateForm(event=event, instance=template)

    placeholders = form.get_valid_placeholders()

    assert "event_name" in placeholders


def test_mail_template_form_grouped_placeholders():
    event = EventFactory()
    form = MailTemplateForm(event=event)

    grouped = form.grouped_placeholders

    assert "event" in grouped
    assert "user" in grouped
    assert any(p.identifier == "event_name" for p in grouped["event"])
    assert all(
        hasattr(p, "rendered_sample") for group in grouped.values() for p in group
    )


def test_mail_template_form_grouped_placeholders_other_category(
    register_signal_handler,
):
    """Placeholders with empty required_context land in the 'other' group
    because they don't match any standard specificity key."""
    event = EventFactory()
    odd_placeholder = SimpleFunctionalMailTextPlaceholder(
        identifier="test_odd", args=[], func=lambda: "test", sample="test"
    )

    def provide_placeholder(signal, sender, **kwargs):
        return odd_placeholder

    register_signal_handler(register_mail_placeholders, provide_placeholder)

    template = MailTemplateFactory(event=event)
    form = MailTemplateForm(event=event, instance=template)
    grouped = form.grouped_placeholders

    assert odd_placeholder in grouped["other"]


def test_mail_template_form_read_only():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, read_only=True, data={"subject_0": "Hello", "text_0": "Body"}
    )

    for field in form.fields.values():
        assert field.disabled is True
    assert not form.is_valid()


def test_mail_template_form_save():
    event = EventFactory()
    form = MailTemplateForm(
        event=event, data={"subject_0": "Test subject", "text_0": "Test body"}
    )
    assert form.is_valid(), form.errors

    template = form.save()

    assert template.pk is not None
    assert template.event == event
    assert str(template.subject) == "Test subject"
    assert str(template.text) == "Test body"
