# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress
from pathlib import Path

from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.path import path_with_hash
from pretalx.common.urls import get_base_url


def resource_path(instance, filename):
    base_path = f"{instance.submission.event.slug}/submissions/{instance.submission.code}/resources/"
    return path_with_hash(filename, base_path=base_path)


class Resource(PretalxModel):
    """Resources are file uploads belonging to a :class:`~pretalx.submission.models.submission.Submission`."""

    log_prefix = "pretalx.submission.resource"

    submission = models.ForeignKey(
        to="submission.Submission", related_name="resources", on_delete=models.PROTECT
    )
    resource = models.FileField(
        verbose_name=_("File"),
        upload_to=resource_path,
        null=True,
        blank=True,
    )
    link = models.URLField(max_length=400, verbose_name=_("URL"), null=True, blank=True)
    description = models.CharField(
        null=True, blank=True, max_length=1000, verbose_name=_("Description")
    )
    is_public = models.BooleanField(
        default=True, verbose_name=_("Publicly visible resource")
    )
    hide_until_event_day = models.BooleanField(
        default=False,
        verbose_name=_("Hide until event day"),
        help_text=_(
            "If enabled, this resource will only be visible on or after the day of the session."
        ),
    )

    objects = ScopedManager(event="submission__event")

    class Meta:
        verbose_name_plural = _("Resources")  # Used to display submission log entries

    def __str__(self):
        """Help when debugging."""
        return f"Resource(event={self.submission.event.slug}, submission={self.submission.title})"

    @cached_property
    def url(self):
        if self.link:
            return self.link
        with suppress(ValueError):
            url = getattr(self.resource, "url", None)
            if url:
                base_url = get_base_url(self.submission.event)
                return base_url + url

    @cached_property
    def filename(self):
        with suppress(ValueError):
            if self.resource:
                return Path(self.resource.name).name

    @cached_property
    def is_available(self):
        """Check if the resource is available based on hide_until_event_day setting.

        If hide_until_event_day is True, the resource is only available on or after
        the start time of the submission's earliest scheduled slot.
        """
        if not self.hide_until_event_day:
            return True

        # Get the earliest slot start time for this submission
        earliest_slot = (
            self.submission.slots.filter(start__isnull=False).order_by("start").first()
        )

        if not earliest_slot or not earliest_slot.start:
            # No scheduled slot yet, so resource is not available
            return False

        # Resource is available if current time is on or after the slot start
        return now() >= earliest_slot.start
