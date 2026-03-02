# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.serializers.mail import MailTemplateSerializer
from tests.factories import EventFactory, MailTemplateFactory
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_serializer_create_sets_event():
    event = EventFactory()
    serializer = MailTemplateSerializer(
        context={"request": make_api_request(event=event)}
    )
    template = serializer.create({"subject": "Test", "text": "Hello"})

    assert template.event == event
    assert template.subject == "Test"
    assert template.text == "Hello"


@pytest.mark.parametrize(
    ("method", "text"),
    (
        ("validate_subject", "Hello {event_name}"),
        ("validate_text", "Dear {name}, welcome to {event_name}"),
    ),
)
def test_mail_template_serializer_validate_accepts_valid_placeholder(method, text):
    template = MailTemplateFactory()
    serializer = MailTemplateSerializer(
        instance=template, context={"request": make_api_request(event=template.event)}
    )

    result = getattr(serializer, method)(text)
    assert result == text


@pytest.mark.parametrize("method", ("validate_subject", "validate_text"))
def test_mail_template_serializer_validate_rejects_unknown_placeholder(method):
    template = MailTemplateFactory()
    serializer = MailTemplateSerializer(
        instance=template, context={"request": make_api_request(event=template.event)}
    )

    with pytest.raises(exceptions.ValidationError, match="totally_invalid_placeholder"):
        getattr(serializer, method)("Hello {totally_invalid_placeholder}")


def test_mail_template_serializer_validate_text_rejects_malformed_braces():
    template = MailTemplateFactory()
    serializer = MailTemplateSerializer(
        instance=template, context={"request": make_api_request(event=template.event)}
    )

    with pytest.raises(exceptions.ValidationError, match="Invalid email template"):
        serializer.validate_text("Hello {unmatched")


def test_mail_template_serializer_validate_text_accepts_plain_text():
    template = MailTemplateFactory()
    serializer = MailTemplateSerializer(
        instance=template, context={"request": make_api_request(event=template.event)}
    )

    result = serializer.validate_text("No placeholders here")
    assert result == "No placeholders here"


def test_mail_template_serializer_validate_text_without_instance_accepts_valid():
    """When no instance exists, valid_placeholders come from a new MailTemplate(event=event)."""
    event = EventFactory()
    serializer = MailTemplateSerializer(
        context={"request": make_api_request(event=event)}
    )

    result = serializer.validate_text("Hello {event_name}")
    assert result == "Hello {event_name}"


def test_mail_template_serializer_validate_text_without_instance_rejects_invalid():
    event = EventFactory()
    serializer = MailTemplateSerializer(
        context={"request": make_api_request(event=event)}
    )

    with pytest.raises(exceptions.ValidationError, match="Unknown placeholder"):
        serializer.validate_text("Hello {nonexistent_var}")


def test_mail_template_serializer_includes_all_fields():
    template = MailTemplateFactory()
    serializer = MailTemplateSerializer(
        template, context={"request": make_api_request(event=template.event)}
    )

    assert set(serializer.data.keys()) == {
        "id",
        "role",
        "subject",
        "text",
        "reply_to",
        "bcc",
    }
