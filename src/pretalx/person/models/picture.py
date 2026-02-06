# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.mixins import FileCleanupMixin, TimestampedModel
from pretalx.common.text.path import hashed_path


def picture_path(instance, filename):
    return hashed_path(
        filename, target_name=instance.user.code or "avatar", upload_dir="avatars"
    )


class ProfilePicture(FileCleanupMixin, TimestampedModel, models.Model):
    user = models.ForeignKey(
        to="person.User",
        related_name="pictures",
        on_delete=models.CASCADE,
    )
    avatar = models.ImageField(
        null=True,
        blank=True,
        verbose_name=_("Profile picture"),
        upload_to=picture_path,
    )
    avatar_thumbnail = models.ImageField(null=True, blank=True, upload_to="avatars/")
    avatar_thumbnail_tiny = models.ImageField(
        null=True, blank=True, upload_to="avatars/"
    )
    get_gravatar = models.BooleanField(
        default=False,
        verbose_name=_("Retrieve profile picture via gravatar"),
    )

    def __str__(self):
        return f"ProfilePicture(user={self.user.code})"
