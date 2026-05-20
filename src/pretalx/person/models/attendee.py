# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models

from pretalx.common.models.mixins import PretalxModel


class AttendeeProfile(PretalxModel):
    user = models.ForeignKey(
        to="person.User", related_name="attendee_profiles", on_delete=models.CASCADE
    )
    event = models.ForeignKey(
        to="event.Event", related_name="attendee_profiles", on_delete=models.CASCADE
    )

    log_prefix = "pretalx.user.attendee"

    class Meta:
        unique_together = (("event", "user"),)

    def __str__(self):
        return f"AttendeeProfile(event={self.event.slug}, user={self.user})"

    @property
    def log_parent(self):
        return self.event
