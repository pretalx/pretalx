# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from i18nfield.fields import I18nCharField

from pretalx.agenda.rules import is_agenda_visible
from pretalx.common.models.fields import DateTimeField
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.event.rules import can_change_event_settings
from pretalx.submission.rules import is_cfp_open, orga_can_change_submissions
from pretalx.submission.validators.type import validate_unique_submission_type_name


def pleasing_number(number):
    if int(number) == number:
        return int(number)
    return number


class SubmissionType(PretalxModel):
    """Each :class:`~pretalx.submission.models.submission.Submission` has one
    SubmissionType.

    SubmissionTypes are used to group submissions by default duration (which
    can be overridden on a per-submission basis), and to be able to offer
    different deadlines for some parts of the
    :class:`~pretalx.event.models.event.Event`.
    """

    event = models.ForeignKey(
        to="event.Event", related_name="submission_types", on_delete=models.CASCADE
    )
    name = I18nCharField(max_length=100, verbose_name=_("Name"))
    default_duration = models.PositiveIntegerField(
        default=30,
        verbose_name=_("default duration"),
        help_text=_("Duration in minutes"),
    )
    deadline = DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Deadline"),
        help_text=_(
            "If you want a different deadline than the global deadline for this session type, enter it here."
        ),
    )
    requires_access_code = models.BooleanField(
        verbose_name=_("Requires access code"),
        help_text=_(
            "This session type will only be shown to submitters with a matching access code."
        ),
        default=False,
    )
    attendee_signup_required = models.BooleanField(
        verbose_name=_("Requires signup"),
        help_text=_(
            "Sessions will require attendee signup by default. "
            "You can always override this setting for individual sessions."
        ),
        default=False,
    )

    log_prefix = "pretalx.submission_type"

    class Meta:
        ordering = ["default_duration"]
        rules_permissions = {
            "list": is_cfp_open | is_agenda_visible | orga_can_change_submissions,
            "view": is_cfp_open | is_agenda_visible | orga_can_change_submissions,
            "orga_list": orga_can_change_submissions,
            "orga_view": orga_can_change_submissions,
            "create": can_change_event_settings,
            "update": can_change_event_settings,
            "delete": can_change_event_settings,
        }

    class urls(EventUrls):
        base = edit = "{self.event.cfp.urls.types}{self.pk}/"
        default = "{base}default/"
        delete = "{base}delete/"
        prefilled_cfp = "{self.event.cfp.urls.public}?submission_type={self.slug}"

    def __str__(self) -> str:
        """Used in choice drop downs."""
        if not self.default_duration:
            return str(self.name)
        if self.default_duration >= 60 * 24:
            days = round(self.default_duration / 60 / 24, 1)
            if days == 1:
                return _("{name} (1 day)").format(name=self.name)
            return _("{name} ({duration} days)").format(
                name=self.name, duration=pleasing_number(days)
            )
        if self.default_duration > 90:
            hours = self.default_duration // 60
            minutes = self.default_duration % 60
            if hours == 1:
                duration = _("1 hour, {minutes} minutes").format(minutes=minutes)
            elif minutes:
                duration = _("{hours} hours, {minutes} minutes").format(
                    hours=hours, minutes=minutes
                )
            else:
                duration = _("{hours} hours").format(hours=hours)
            return f"{self.name} ({duration})"
        return _("{name} ({duration} minutes)").format(
            name=self.name, duration=self.default_duration
        )

    @property
    def log_parent(self):
        return self.event

    @property
    def slug(self) -> str:
        """The slug makes tracks more readable in URLs.

        It consists of the ID, followed by a slugified (and, in lookups,
        optional) form of the submission type name.
        """
        return f"{self.id}-{slugify(self.name)}"

    def delete(self, *args, **kwargs):
        from pretalx.submission.domain.access_code import (  # noqa: PLC0415 -- thin method
            delete_orphan_access_codes,
        )

        delete_orphan_access_codes(self.submitter_access_codes, "submission_types")
        return super().delete(*args, **kwargs)

    delete.alters_data = True

    def clean(self):
        super().clean()
        validate_unique_submission_type_name(self)
