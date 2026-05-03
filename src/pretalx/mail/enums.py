# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


class QueuedMailStates(models.TextChoices):
    DRAFT = "draft", pgettext_lazy("email status", "Draft")
    SENDING = "sending", pgettext_lazy("email status", "Sending")
    SENT = "sent", pgettext_lazy("email status", "Sent")


class MailTemplateRoles(models.TextChoices):
    NEW_SUBMISSION = "submission.new", _("Acknowledge proposal submission")
    NEW_SUBMISSION_INTERNAL = (
        "submission.new.internal",
        _("New proposal (organiser notification)"),
    )
    SUBMISSION_ACCEPT = "submission.state.accepted", _("Proposal accepted")
    SUBMISSION_REJECT = "submission.state.rejected", _("Proposal rejected")
    NEW_SPEAKER_INVITE = (
        "speaker.invite",
        _("Add a speaker to a proposal (new account)"),
    )
    EXISTING_SPEAKER_INVITE = (
        "speaker.invite.existing",
        _("Add a speaker to a proposal (existing account)"),
    )
    QUESTION_REMINDER = "question.reminder", _("Custom fields reminder")
    DRAFT_REMINDER = "draft.reminder", _("Draft proposal reminder")
    NEW_SCHEDULE = "schedule.new", _("New schedule published")
