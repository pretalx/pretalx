# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from enum import StrEnum, nonmember

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


class SubmissionStates(models.TextChoices):
    SUBMITTED = "submitted", pgettext_lazy("proposal status", "submitted")
    ACCEPTED = "accepted", _("accepted")
    CONFIRMED = "confirmed", _("confirmed")
    REJECTED = "rejected", _("rejected")
    CANCELED = "canceled", _("Cancelled")
    WITHDRAWN = "withdrawn", _("withdrawn")
    DRAFT = "draft", pgettext_lazy("proposal status", "Draft")

    accepted_states = nonmember(("accepted", "confirmed"))
    public_review_states = nonmember(("submitted", "draft", *accepted_states))
    log_actions = nonmember(
        {
            "submitted": ".make_submitted",
            "accepted": ".accept",
            "rejected": ".reject",
            "confirmed": ".confirm",
            "canceled": ".cancel",
            "withdrawn": ".withdraw",
        }
    )

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)

    @staticmethod
    def get_color(state):
        return {
            "submitted": "--color-info",
            "accepted": "--color-success",
            "confirmed": "--color-success",
            "rejected": "--color-danger",
        }.get(state, "--color-grey")


class AttendeeSignupStates(models.TextChoices):
    CONFIRMED = "confirmed", pgettext_lazy("attendee signup status", "confirmed")
    CANCELED = "canceled", pgettext_lazy("attendee signup status", "cancelled")

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)


class SignupStatus(StrEnum):
    OPEN = "open"
    FULL = "full"


class QuestionVariant(models.TextChoices):
    NUMBER = "number", _("Number")
    STRING = "string", _("Text (one-line)")
    TEXT = "text", _("Multi-line text")
    URL = "url", _("URL")
    DATE = "date", pgettext_lazy("question field type", "Date")
    DATETIME = "datetime", _("Date and time")
    BOOLEAN = "boolean", _("Yes/No")
    FILE = "file", _("File upload")
    CHOICES = "choices", _("Choose one from a list")
    MULTIPLE = "multiple_choice", _("Choose multiple from a list")

    short_answers = nonmember(
        (
            "number",
            "string",
            "url",
            "date",
            "datetime",
            "boolean",
            "file",
            "choices",
            "multiple_choice",
        )
    )
    long_answers = nonmember(("text",))

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)


class QuestionTarget(models.TextChoices):
    SUBMISSION = "submission", _("per proposal")
    SPEAKER = "speaker", _("per speaker")
    REVIEWER = "reviewer", _("for reviewers")

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)


class QuestionRequired(models.TextChoices):
    OPTIONAL = "optional", _("always optional")
    REQUIRED = "required", _("always required")
    AFTER_DEADLINE = "after_deadline", _("required after a deadline")

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)


class QuestionIcon(models.TextChoices):
    NONE = "-", _("No icon")
    BSKY = "bsky", _("Bluesky")
    DISCORD = "discord", _("Discord")
    GITHUB = "github", _("GitHub")
    INSTAGRAM = "instagram", _("Instagram")
    LINKEDIN = "linkedin", _("LinkedIn")
    MASTODON = "mastodon", _("Mastodon")
    TWITTER = "twitter", _("Twitter")
    WEB = "web", _("Website")
    YOUTUBE = "youtube", _("YouTube")

    @classmethod
    def get_max_length(cls):
        return max(len(val) for val in cls.values)
