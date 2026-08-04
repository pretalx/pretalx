# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Andreas Hubel

import uuid
from functools import cached_property

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField

from pretalx.agenda.rules import is_agenda_visible
from pretalx.common.models.mixins import OrderedModel, PretalxModel
from pretalx.common.models.settings import GlobalSettings
from pretalx.common.urls import EventUrls
from pretalx.event.rules import can_change_event_settings
from pretalx.schedule.models.availability import Availability
from pretalx.submission.rules import orga_can_change_submissions

ROOM_IN_USE_ERROR = _(
    "This room has sessions in the current or the planned schedule, so it can neither be deleted nor hidden."
)


class RoomQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(hidden=False)


class RoomManager(models.Manager.from_queryset(RoomQuerySet)):
    pass


class Room(OrderedModel, PretalxModel):
    """A Room is an actual place where talks will be scheduled.

    The Room object stores some meta information. Most, like capacity,
    are not in use right now.
    """

    log_prefix = "pretalx.room"

    event = models.ForeignKey(
        to="event.Event", on_delete=models.PROTECT, related_name="rooms"
    )
    name = I18nCharField(max_length=100, verbose_name=_("Name"))
    guid = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=_("GUID"),
        help_text=_(
            "Unique identifier (UUID) to help external tools identify the room."
        ),
    )
    description = I18nCharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("A description for attendees, for example directions."),
    )
    speaker_info = I18nCharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("Speaker Information"),
        help_text=_(
            "Information relevant for speakers scheduled in this room, for example room size, special directions, available adaptors for video input …"
        ),
    )
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Capacity"),
        help_text=_("How many people can fit in the room?"),
        validators=[MinValueValidator(1)],
    )
    position = models.PositiveIntegerField(null=True, blank=True)
    hidden = models.BooleanField(
        default=False,
        verbose_name=_("Hidden"),
        help_text=_(
            "Hidden rooms are not offered for scheduling and do not show up in the schedule editor. Past schedule versions keep showing them."
        ),
    )

    objects = ScopedManager(event="event", _manager_class=RoomManager)

    class Meta:
        ordering = ("position",)
        unique_together = ("event", "guid")
        rules_permissions = {
            "list": is_agenda_visible | orga_can_change_submissions,
            "view": is_agenda_visible | orga_can_change_submissions,
            "orga_list": orga_can_change_submissions,
            "orga_view": orga_can_change_submissions,
            "create": can_change_event_settings,
            "update": can_change_event_settings,
            "delete": can_change_event_settings,
        }

    class urls(EventUrls):
        settings_base = edit = "{self.event.orga_urls.room_settings}{self.pk}/"
        delete = "{settings_base}delete/"
        hide = "{settings_base}hide/"
        unhide = "{settings_base}unhide/"

    def __str__(self) -> str:
        return str(self.name)

    @property
    def log_parent(self):
        return self.event

    @staticmethod
    def get_order_queryset(event):
        return event.rooms.all()

    def clean(self):
        super().clean()
        if self.hidden and self.pk and self.is_in_use:
            raise ValidationError({"hidden": ROOM_IN_USE_ERROR})

    @property
    def is_deletable(self) -> bool:
        if (has_slots := getattr(self, "has_slots", None)) is not None:
            return not has_slots
        return not self.talks.exists()

    @property
    def is_in_use(self) -> bool:
        if (in_use := getattr(self, "has_scheduled_slots", None)) is not None:
            return in_use
        from pretalx.schedule.domain.room import (  # noqa: PLC0415 -- thin method
            room_is_in_use,
        )

        return room_is_in_use(self)

    @cached_property
    def uuid(self):
        """Either a UUID5 calculated from the submission code and the instance identifier;
        or GUID value of the room, if it was imported or set manually."""
        if self.guid:
            return self.guid

        if self._state.adding:
            return ""

        return uuid.uuid5(GlobalSettings().get_instance_identifier(), f"room:{self.pk}")

    @property
    def slug(self) -> str:
        """The slug makes tracks more readable in URLs.

        It consists of the ID, followed by a slugified (and, in lookups,
        optional) form of the track name.
        """
        return f"{self.id}-{slugify(self.name)}"

    @cached_property
    def full_availability(self):
        return Availability.union(self.availabilities.all())
