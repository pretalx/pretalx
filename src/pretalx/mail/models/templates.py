# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretalx.common.models.mixins import PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.mail.enums import MailTemplateRoles
from pretalx.mail.validators import validate_text_no_empty_links
from pretalx.submission.rules import orga_can_change_submissions


class MailTemplate(PretalxModel):
    """MailTemplates can be used to create.

    :class:`~pretalx.mail.models.QueuedMail` objects.

    The process does not come with variable substitution except for
    special cases, for now.
    """

    log_prefix = "pretalx.mail_template"

    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="mail_templates"
    )
    role = models.CharField(
        choices=MailTemplateRoles.choices,
        max_length=30,
        null=True,
        default=None,
        editable=False,
    )
    subject = I18nCharField(
        max_length=200, verbose_name=pgettext_lazy("email subject", "Subject")
    )
    text = I18nTextField(verbose_name=_("Text"))
    reply_to = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Reply-To"),
        help_text=_(
            "Change the Reply-To address if you do not want to use the default organiser address"
        ),
    )
    bcc = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name=_("BCC"),
        help_text=_(
            "Enter comma separated addresses. Will receive a blind copy of every email sent from this template. This may be a LOT!"
        ),
    )
    # Auto-created templates are created when mass emails are sent out. They are only used to re-create similar
    # emails, and are never shown in a list of email templates or anywhere else.
    is_auto_created = models.BooleanField(default=False)

    objects = ScopedManager(event="event")

    class Meta:
        unique_together = (("event", "role"),)
        rules_permissions = {
            "list": orga_can_change_submissions,
            "view": orga_can_change_submissions,
            "create": orga_can_change_submissions,
            "update": orga_can_change_submissions,
            "delete": orga_can_change_submissions,
        }

    class urls(EventUrls):
        base = edit = "{self.event.orga_urls.mail_templates}{self.pk}/"
        delete = "{base}delete/"

    def __str__(self):
        """Help with debugging."""
        return f"MailTemplate(event={self.event.slug}, subject={self.subject})"

    @property
    def log_parent(self):
        return self.event

    def clean(self):
        # Centralised here so both the modelform and the API serializer
        # (which calls full_clean via the serializer base mixin) catch
        # markdown links with empty hrefs.
        from pretalx.mail.domain.placeholders import (  # noqa: PLC0415 -- thin method
            placeholders_for_template,
        )

        super().clean()
        if not self.text or not self.event_id:
            return
        try:
            validate_text_no_empty_links(
                self.text, placeholders_for_template(self), self.event
            )
        except ValidationError as exc:
            raise ValidationError({"text": exc.messages}) from exc
