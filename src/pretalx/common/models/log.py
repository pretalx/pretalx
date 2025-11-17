# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import logging
from contextlib import suppress

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
from django.utils.functional import cached_property
from django_scopes import ScopedManager


class ActivityLog(models.Model):
    """This model logs actions within an event.

    It is **not** designed to provide a complete or reliable audit
    trail.

    :param is_orga_action: True, if the logged action was performed by a privileged user.
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
    content_object = GenericForeignKey("content_type", "object_id")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action_type = models.CharField(max_length=200)
    legacy_data = models.TextField(null=True, blank=True)
    data = models.JSONField(null=True, blank=True, default=dict)
    is_orga_action = models.BooleanField(default=False)

    objects = ScopedManager(event="event")

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        """Custom __str__ to help with debugging."""
        event = getattr(self.event, "slug", "None")
        person = getattr(self.person, "name", "None")
        return f"ActivityLog(event={event}, person={person}, content_object={self.content_object}, action_type={self.action_type})"

    @cached_property
    def json_data(self):
        if self.data is not None:
            return self.data
        if self.legacy_data:
            with suppress(json.JSONDecodeError):
                return json.loads(self.legacy_data)
        return {}

    @cached_property
    def display(self) -> str:
        from pretalx.common.signals import activitylog_display

        for _receiver, response in activitylog_display.send(
            self.event, activitylog=self
        ):
            if response:
                return response

        logger = logging.getLogger(__name__)
        logger.warning(f'Unknown log action "{self.action_type}".')
        return self.action_type

    @cached_property
    def display_object(self) -> str:
        """Returns a link (formatted HTML) to the object in question."""
        from pretalx.common.signals import activitylog_object_link

        if not self.content_object:
            return ""

        responses = activitylog_object_link.send(sender=self.event, activitylog=self)
        if responses:
            for _receiver, response in responses:
                if response:
                    return response
        return ""

    @cached_property
    def changes(self):
        if not self.data or not self.event or not self.data.get("changes"):
            return
        object = self.content_object
        if not object:
            return
        result = {}
        for key, value in self.data["changes"].items():
            display = value.copy()
            if not value.get("old") and not value.get("new"):
                continue
            if key.startswith("question-"):
                question_pk = key.split("-", 1)[-1]
                question = self.event.questions.filter(pk=question_pk).first()
                if question:
                    display["question"] = question
                    display["label"] = question.question
            else:
                try:
                    if field := object.__class__._meta.get_field(key):
                        display["field"] = field
                        if isinstance(field, (ManyToOneRel, ManyToManyRel)):
                            display["label"] = (
                                field.related_model._meta.verbose_name_plural
                            )
                        else:
                            display["label"] = field.verbose_name
                except FieldDoesNotExist:
                    display["label"] = key.capitalize()
            result[key] = display
        return result
