# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretalx.common.models.log import ActivityLog
from pretalx.common.models.mixins import OrderedModel, PretalxModel
from pretalx.submission.enums import AttendeeSignupStates


class AttendeeSignup(OrderedModel, PretalxModel):
    submission = models.ForeignKey(
        to="submission.Submission",
        on_delete=models.CASCADE,
        related_name="attendee_signups",
    )
    attendee = models.ForeignKey(
        to="person.AttendeeProfile", on_delete=models.CASCADE, related_name="signups"
    )
    state = models.CharField(
        max_length=AttendeeSignupStates.get_max_length(),
        choices=AttendeeSignupStates.choices,
        default=AttendeeSignupStates.CONFIRMED,
        verbose_name=_("Signup state"),
    )
    position = models.PositiveIntegerField(default=0)

    objects = ScopedManager(event="submission__event")

    log_prefix = "pretalx.submission.signup"

    class Meta:
        ordering = ("position", "id")
        unique_together = (("submission", "attendee"),)

    def __str__(self):
        return (
            f"AttendeeSignup(submission={self.submission.code}, "
            f"attendee={self.attendee}, state={self.state})"
        )

    @cached_property
    def event(self):
        return self.submission.event

    @property
    def log_parent(self):
        return self.submission

    @property
    def order_queryset(self):
        return self.get_order_queryset(submission=self.submission)

    @staticmethod
    def get_order_queryset(submission):
        return submission.attendee_signups.all()

    def log_action(self, *args, **kwargs):
        # We log on the submission object so signups show up on the
        # submission history.
        kwargs.setdefault("content_object", self.submission)
        return super().log_action(*args, **kwargs)

    def logged_actions(self):
        return (
            ActivityLog.objects.filter(
                content_type=ContentType.objects.get_for_model(type(self.submission)),
                object_id=self.submission.pk,
                action_type__startswith=f"{self.log_prefix}.",
                person=self.attendee.user,
            )
            .select_related("event", "person")
            .prefetch_related("content_object")
        )
