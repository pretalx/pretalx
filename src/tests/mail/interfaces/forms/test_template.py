# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re

import pytest
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from pretalx.mail.domain.placeholders import (
    BaseMailTextPlaceholder,
    TrustedPlainMailTextPlaceholder,
)
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.interfaces.forms.template import MailTemplateForm
from pretalx.mail.signals import register_mail_placeholders
from tests.factories import EventFactory, MailTemplateFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("kwargs", ({}, {"event": None}), ids=("missing", "none"))
def test_mail_template_form_requires_event(kwargs):
    with pytest.raises(TypeError):
        MailTemplateForm(**kwargs)


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {
                "subject_0": "Hello {event_name}",
                "text_0": "Visit [our site](https://example.com) please",
            },
            [],
        ),
        ({"subject_0": "", "text_0": "World"}, ["subject"]),
        ({"subject_0": "Hello", "text_0": ""}, ["text"]),
        (
            {"subject_0": "Hello {nonexistent_placeholder}", "text_0": "Body text"},
            ["subject"],
        ),
        ({"subject_0": "Hello", "text_0": "Body {does_not_exist}"}, ["text"]),
        ({"subject_0": "Hello { broken", "text_0": "Body text"}, ["subject"]),
        ({"subject_0": "Hello", "text_0": "Body { broken"}, ["text"]),
        # Empty-link rejection lives on MailTemplate.clean(); the modelform's
        # _post_clean path runs full_clean, so the error reaches form.errors["text"].
        ({"subject_0": "Hello", "text_0": "[Click here]()"}, ["text"]),
    ),
    ids=(
        "valid",
        "subject_required",
        "text_required",
        "subject_unknown_placeholder",
        "text_unknown_placeholder",
        "subject_malformed",
        "text_malformed",
        "text_empty_link",
    ),
)
def test_mail_template_form_clean(data, errors):
    form = MailTemplateForm(event=EventFactory(), data=data)

    assert form.is_valid() == (not errors), form.errors
    assert list(form.errors) == errors


def test_mail_template_form_groups_valid_placeholders():
    event = EventFactory()
    template = MailTemplateFactory(event=event)
    form = MailTemplateForm(event=event, instance=template)

    assert "event_name" in form.get_valid_placeholders()
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
    event = EventFactory()
    odd_placeholder = TrustedPlainMailTextPlaceholder(
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


class PluginPlaceholder(BaseMailTextPlaceholder):
    identifier = "plugin_greeting"

    def render(self, context):
        return f"Hello from {context['event'].name}"

    def render_sample(self, event):
        return "Hello from DemoCon"


def _register_plugin_placeholder(register_signal_handler):
    placeholder = PluginPlaceholder()

    def provide_placeholder(signal, sender, **kwargs):
        return placeholder

    register_signal_handler(register_mail_placeholders, provide_placeholder)
    return placeholder


def test_mail_template_form_offers_and_saves_plugin_placeholder(
    register_signal_handler,
):
    event = EventFactory()
    placeholder = _register_plugin_placeholder(register_signal_handler)
    template = MailTemplateFactory(event=event)

    form = MailTemplateForm(event=event, instance=template)

    assert placeholder in form.grouped_placeholders["event"]
    form = MailTemplateForm(
        event=event,
        instance=template,
        data={"subject_0": "Hi", "text_0": "{plugin_greeting}"},
    )
    assert form.is_valid(), form.errors

    saved = form.save()

    assert saved.pk == template.pk
    assert saved.event == event
    assert str(saved.subject) == "Hi"
    assert str(saved.text) == "{plugin_greeting}"
    assert str(render_template_to_mail(saved).text) == f"Hello from {event.name}"


def test_placeholder_picker_renders_plugin_placeholder_without_explanation(
    register_signal_handler,
):
    event = EventFactory()
    _register_plugin_placeholder(register_signal_handler)
    form = MailTemplateForm(event=event, instance=MailTemplateFactory(event=event))

    html = render_to_string(
        "orga/mails/_placeholder_group.html",
        {"placeholders": form.grouped_placeholders["event"], "tag": "event"},
    )

    detail = re.search(
        r'id="collapseplugin_greeting".*?>(.*?)</small>', html, re.DOTALL
    ).group(1)
    assert (
        " ".join(strip_tags(detail).split()).lstrip(", ") == "e.g. Hello from DemoCon"
    )
