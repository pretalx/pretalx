# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework.serializers import HiddenField

from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.mail.domain.placeholders import placeholders_for_template
from pretalx.mail.models import MailTemplate
from pretalx.mail.validators import validate_text_placeholders


@register_serializer(versions=CURRENT_VERSIONS)
class MailTemplateSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = MailTemplate
        fields = ("id", "role", "subject", "text", "reply_to", "bcc", "event")

    def validate_subject(self, value):
        template = self.instance or MailTemplate(event=self.event)
        validate_text_placeholders(value, placeholders_for_template(template))
        return value

    def validate_text(self, value):
        template = self.instance or MailTemplate(event=self.event)
        validate_text_placeholders(value, placeholders_for_template(template))
        return value
