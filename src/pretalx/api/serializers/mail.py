# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework import exceptions
from rest_framework.serializers import HiddenField

from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.mail.domain.placeholders import (
    get_invalid_placeholders,
    placeholders_for_template,
)
from pretalx.mail.models import MailTemplate


@register_serializer(versions=CURRENT_VERSIONS)
class MailTemplateSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = MailTemplate
        fields = ("id", "role", "subject", "text", "reply_to", "bcc", "event")

    def _validate_text(self, value):
        template = self.instance or MailTemplate(event=self.event)
        try:
            fields = get_invalid_placeholders(
                value, placeholders_for_template(template)
            )
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
