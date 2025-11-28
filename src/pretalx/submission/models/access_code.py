# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import math

from django.core import validators
from django.db import models
from django.utils.timezone import now
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.fields import DateTimeField
from pretalx.common.models.mixins import GenerateCode, PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.event.rules import can_change_event_settings


class SubmitterAccessCode(GenerateCode, PretalxModel):
    event = models.ForeignKey(
        to="event.Event",
        on_delete=models.CASCADE,
        related_name="submitter_access_codes",
    )
    code = models.CharField(
        verbose_name=_("Access code"),
        max_length=255,
        db_index=True,
        validators=[validators.RegexValidator("^[a-zA-Z0-9]+$")],
    )
    track = models.ForeignKey(
        to="submission.Track",
        on_delete=models.CASCADE,
        verbose_name=_("Track"),
        help_text=_(
            "You can restrict the access code to a single track, or leave it open for all tracks."
        ),
        related_name="submitter_access_codes",
        null=True,
        blank=True,
    )
    submission_type = models.ForeignKey(
        to="submission.SubmissionType",
        on_delete=models.CASCADE,
        verbose_name=_("Session type"),
        help_text=_(
            "You can restrict the access code to a single session type, or leave it open for all session types."
        ),
        related_name="submitter_access_codes",
        null=True,
        blank=True,
    )
    valid_until = DateTimeField(
        verbose_name=_("Valid until"),
        help_text=_(
            "You can set or change this date later to invalidate the access code."
        ),
        null=True,
        blank=True,
    )
    maximum_uses = models.PositiveIntegerField(
        verbose_name=_("Maximum uses"),
        help_text=_(
            "Numbers of times this access code can be used to submit a proposal. Leave empty for no limit."
        ),
        default=1,
        null=True,
        blank=True,
    )
    redeemed = models.PositiveIntegerField(
        verbose_name=_("Redeemed"), default=0, editable=False
    )
    internal_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Internal notes"),
        help_text=_(
            "Internal notes for other organisers/reviewers. Not visible to the speakers or the public."
        ),
    )

    _code_length = 32

    log_prefix = "pretalx.access_code"

    class Meta:
        unique_together = (("event", "code"),)
        rules_permissions = {
            "list": can_change_event_settings,
            "view": can_change_event_settings,
            "create": can_change_event_settings,
            "update": can_change_event_settings,
            "delete": can_change_event_settings,
        }

    class urls(EventUrls):
        base = edit = "{self.event.cfp.urls.access_codes}{self.code}/"
        send = "{base}send"
        delete = "{base}delete/"
        cfp_url = "{self.event.cfp.urls.public}?access_code={self.code}"

    @property
    def log_parent(self):
        return self.event

    @property
    def redemptions_valid(self):
        return self.maximum_uses - self.redeemed > 0 if self.maximum_uses else True

    @property
    def time_valid(self):
        return now() < self.valid_until if self.valid_until else True

    @property
    def is_valid(self):
        return self.time_valid and self.redemptions_valid

    @property
    def redemptions_left(self):
        if not self.maximum_uses:
            return math.inf
        return self.maximum_uses - self.redeemed

    def send_invite(self, to, subject, text):
        from pretalx.mail.models import QueuedMail

        to = to.split(",") if isinstance(to, str) else to
        for invite in to:
            QueuedMail(
                event=self.event,
                to=invite,
                subject=subject,
                text=text,
                locale=get_language(),
            ).send()

    send_invite.alters_data = True

    def _get_instance_data(self):
        result = super()._get_instance_data()
        result["code"] = self.code  # Usually excluded as ID field
        return result
