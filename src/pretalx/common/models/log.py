# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property

from pretalx.common.models.fields import StaleTolerantGenericForeignKey
from pretalx.common.models.managers import ScopedManager
from pretalx.common.signals import activitylog_display, activitylog_object_link


class ActivityLog(models.Model):
    """This model logs changes and actions taken by users and automations.

    It is **not** designed to provide a complete or reliable audit trail.
    See :class:`pretalx.common.models.mixins.LogMixin` for the corresponding
    mixin used by most other models.
    """

    event = models.ForeignKey(
        to="event.Event",
        on_delete=models.PROTECT,
        related_name="log_entries",
        null=True,
        blank=True,
    )
    person = models.ForeignKey(
        to="person.User",
        on_delete=models.PROTECT,
        related_name="log_entries",
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(to=ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = StaleTolerantGenericForeignKey("content_type", "object_id")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action_type = models.CharField(max_length=200)
    data = models.JSONField(null=True, blank=True, default=dict)
    is_orga_action = models.BooleanField(default=False)

    objects = ScopedManager(event="event")

    class Meta:
        ordering = ("-timestamp", "-pk")

    def __str__(self):
        event = getattr(self.event, "slug", "None")
        person = getattr(self.person, "name", "None")
        return f"ActivityLog(event={event}, person={person}, content_object={self.content_object}, action_type={self.action_type})"

    @cached_property
    def json_data(self):
        # Kept for backwards compatibility, as well as to avoid None-checks
        return self.data or {}

    @cached_property
    def display(self) -> str:
        for _receiver, response in activitylog_display.send(
            self.event, activitylog=self
        ):
            if response:
                return response

        logger = logging.getLogger(__name__)
        logger.warning('Unknown log action "%s".', self.action_type)
        return self.action_type

    @cached_property
    def person_display_name(self) -> str:
        if not self.person_id:
            return ""
        if self.event_id:
            from pretalx.common.log import (  # noqa: PLC0415 -- circular import
                speaker_names_for_logs,
            )

            # When used in bulk, should have group_activity_log run to get data.
            if name := speaker_names_for_logs([self]).get(
                (self.event_id, self.person_id)
            ):
                return name
        return self.person.get_display_name()

    @cached_property
    def display_object(self) -> str:
        """A link (formatted HTML) to the object in question."""
        if not self.content_object:
            return ""

        for _receiver, response in activitylog_object_link.send(
            sender=self.event, activitylog=self
        ):
            if response:
                return response
        return ""

    @cached_property
    def detail_url(self) -> str:
        if self.event:
            return reverse(
                "orga:event.history.detail",
                kwargs={"event": self.event.slug, "pk": self.pk},
            )
        return reverse("orga:admin.log.detail", kwargs={"pk": self.pk})

    @cached_property
    def changes(self):
        from pretalx.common.log import (  # noqa: PLC0415 -- thin method
            resolve_log_changes,
        )

        return resolve_log_changes(self)
