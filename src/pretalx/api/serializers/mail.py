# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework import exceptions
from rest_framework.serializers import HiddenField

from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.mail.context import get_invalid_placeholders
from pretalx.mail.models import MailTemplate


@register_serializer(versions=CURRENT_VERSIONS)
class MailTemplateSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = MailTemplate
        fields = ("id", "role", "subject", "text", "reply_to", "bcc", "event")

    def _validate_text(self, value):
        if not self.instance:
            valid_placeholders = MailTemplate(event=self.event).valid_placeholders
        else:
            valid_placeholders = self.instance.valid_placeholders
        try:
            fields = get_invalid_placeholders(value, valid_placeholders)
        except ValueError:
            raise exceptions.ValidationError(
                "Invalid email template! "
                "Please check that you don’t have stray { or } somewhere, "
                "and that there are no spaces inside the {} blocks."
            ) from None
        if fields:
            fields = ", ".join("{" + field + "}" for field in fields)
            raise exceptions.ValidationError(f"Unknown placeholder! {fields}")
        return value

    def validate_subject(self, value):
        return self._validate_text(value)

    def validate_text(self, value):
        return self._validate_text(value)
