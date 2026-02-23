# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.image import create_thumbnail
from pretalx.common.models.mixins import FileCleanupMixin, TimestampedModel
from pretalx.common.text.path import hashed_path


def picture_path(instance, filename):
    return hashed_path(
        filename, target_name=instance.user.code or "avatar", upload_dir="avatars"
    )


class ProfilePictureMixin:
    """Mixin for models that have a profile_picture FK to ProfilePicture."""

    @cached_property
    def avatar(self):
        if self.profile_picture_id:
            return self.profile_picture.avatar

    @cached_property
    def avatar_url(self):
        if self.profile_picture_id:
            return self.profile_picture.get_avatar_url(
                event=getattr(self, "event", None)
            )

    def set_avatar(self, file):
        user = getattr(self, "user", None)
        old_picture = self.profile_picture
        new_picture = ProfilePicture.objects.create(user=user or self, avatar=file)
        new_picture.process_image("avatar", generate_thumbnail=True)
        self.profile_picture = new_picture
        self.save(update_fields=["profile_picture"])
        if old_picture:
            old_picture.save(update_fields=["updated"])
        if user and not user.profile_picture:
            user.profile_picture = new_picture
            user.save(update_fields=["profile_picture"])
        return new_picture


class ProfilePicture(FileCleanupMixin, TimestampedModel, models.Model):
    user = models.ForeignKey(
        to="person.User", related_name="pictures", on_delete=models.CASCADE
    )
    avatar = models.ImageField(
        null=True, blank=True, verbose_name=_("Profile picture"), upload_to=picture_path
    )
    avatar_thumbnail = models.ImageField(null=True, blank=True, upload_to="avatars/")
    avatar_thumbnail_tiny = models.ImageField(
        null=True, blank=True, upload_to="avatars/"
    )

    def __str__(self):
        return f"ProfilePicture(user={self.user.code})"

    @cached_property
    def has_avatar(self):
        return bool(self.avatar) and self.avatar != "False"

    @cached_property
    def avatar_url(self):
        if self.has_avatar:
            return self.avatar.url

    def get_avatar_url(self, event=None, thumbnail=None):
        if not self.avatar_url:
            return ""
        if not thumbnail:
            image = self.avatar
        else:
            image = (
                self.avatar_thumbnail_tiny
                if thumbnail == "tiny"
                else self.avatar_thumbnail
            )
            if not image:
                image = create_thumbnail(self.avatar, thumbnail)
        if not image:
            return
        if event and event.custom_domain:
            return urljoin(event.custom_domain, image.url)
        return urljoin(settings.SITE_URL, image.url)
