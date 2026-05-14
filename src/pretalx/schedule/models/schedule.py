# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from i18nfield.fields import I18nTextField

from pretalx.agenda.rules import can_view_schedule, is_agenda_visible, is_widget_visible
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import EventUrls
from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.rules import is_reviewer
from pretalx.schedule.enums import SlotType
from pretalx.schedule.models.availability import Availability
from pretalx.schedule.validators.schedule import validate_unique_version
from pretalx.submission.models import Submission
from pretalx.submission.rules import is_wip, orga_can_change_submissions


class Schedule(PretalxModel):
    """The Schedule model contains all scheduled.

    :class:`~pretalx.schedule.models.slot.TalkSlot` objects (visible or not)
    for a schedule release for an :class:`~pretalx.event.models.event.Event`.

    :param published: ``None`` if the schedule has not been published yet.
    """

    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="schedules"
    )
    version = models.CharField(
        max_length=190,
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("Version of the conference schedule", "Version"),
    )
    published = models.DateTimeField(null=True, blank=True)
    comment = I18nTextField(
        null=True,
        blank=True,
        help_text=_("This text will be shown in the public changelog and the RSS feed.")
        + " "
        + phrases.base.use_markdown,
    )

    class Meta:
        ordering = ("-published",)
        unique_together = (("event", "version"),)
        rules_permissions = {
            "list": can_view_schedule,
            "view_widget": is_widget_visible | orga_can_change_submissions,
            "view": (~is_wip & is_agenda_visible)
            | orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "orga_view": orga_can_change_submissions
            | (is_reviewer & can_view_speaker_names),
            "export": orga_can_change_submissions,
            "release": orga_can_change_submissions,
        }

    class urls(EventUrls):
        public = "{self.event.urls.schedule}v/{self.url_version}/"
        widget_data = "{public}widgets/schedule.json"
        nojs = "{public}nojs"

    @cached_property
    def scheduled_talks(self):
        """Returns all :class:`~pretalx.schedule.models.slot.TalkSlot` objects
        that have been scheduled and are visible in the schedule (that is, have
        been confirmed at the time of release)."""
        return (
            self.talks.select_related("submission", "submission__event", "room")
            .with_sorted_speakers()
            .filter(
                room__isnull=False,
                start__isnull=False,
                is_visible=True,
                submission__isnull=False,
            )
        )

    @cached_property
    def breaks(self):
        return self.talks.select_related("room").filter(slot_type=SlotType.BREAK)

    @cached_property
    def blockers(self):
        return self.talks.select_related("room").filter(slot_type=SlotType.BLOCKER)

    @cached_property
    def slots(self):
        """Returns all.

        :class:`~pretalx.submission.models.submission.Submission` objects with
        :class:`~pretalx.schedule.models.slot.TalkSlot` objects in this
        schedule.
        """
        return Submission.objects.filter(
            id__in=self.scheduled_talks.values_list("submission", flat=True)
        ).select_related("event", "track", "submission_type")

    @cached_property
    def previous_schedule(self):
        """Returns the schedule released before this one, if any."""
        queryset = self.event.schedules.exclude(pk=self.pk)
        if self.published:
            queryset = queryset.filter(published__lt=self.published)
        return queryset.order_by("-published").first()

    @cached_property
    def changes(self) -> dict:
        """Returns a dictionary of changes when compared to the previous
        version.

        The ``action`` field is either ``create`` or ``update``. If it's
        an update, the ``count`` integer, and the ``new_talks``,
        ``canceled_talks`` and ``moved_talks`` lists are also present.

        This property uses caching with different TTLs:
        - WIP schedules: 60 seconds
        - Released schedules: 10 minutes
        """
        from pretalx.schedule.domain.changes import (  # noqa: PLC0415 -- thin method
            get_cached_schedule_changes,
        )

        return get_cached_schedule_changes(self)

    @cached_property
    def use_room_availabilities(self):
        return Availability.objects.filter(
            room__isnull=False, event=self.event
        ).exists()

    @cached_property
    def warnings(self) -> dict:
        from pretalx.schedule.domain.warnings import (  # noqa: PLC0415 -- thin method
            compute_warnings,
        )

        return compute_warnings(self)

    @cached_property
    def speakers_concerned(self):
        from pretalx.schedule.domain.notifications import (  # noqa: PLC0415 -- thin method
            compute_speakers_concerned,
        )

        return compute_speakers_concerned(self)

    @cached_property
    def version_with_fallback(self):
        return self.version or "wip"

    @cached_property
    def url_version(self):
        return quote(self.version_with_fallback)

    @cached_property
    def is_archived(self):
        if not self.version:
            return False

        return self != self.event.current_schedule

    def __str__(self) -> str:
        """Help when debugging."""
        return f"Schedule(event={self.event.slug}, version={self.version})"

    def clean(self):
        super().clean()
        try:
            validate_unique_version(
                self.version,
                event=self.event if self.event_id else None,
                exclude_schedule=self,
            )
        except ValidationError as exc:
            raise ValidationError({"version": exc.messages}) from exc
