# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

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
        """Relative avatar URL, safe for use in HTML templates served from any
        host (main site or an event's custom domain).

        For absolute URLs (API responses, exports, widget data, emails), use
        :meth:`get_avatar_url` instead.
        """
        if self.profile_picture_id:
            return self.profile_picture.avatar_url

    def get_avatar_url(self, event=None, thumbnail=None):
        """Absolute avatar URL, optionally for a thumbnail size.

        When the related event has a custom domain, that domain is used as
        the base; otherwise ``settings.SITE_URL`` is used. ``event`` defaults
        to ``self.event`` when the model defines one (e.g. ``SpeakerProfile``).
        """
        if not self.profile_picture_id:
            return ""
        if event is None:
            event = getattr(self, "event", None)
        return self.profile_picture.get_avatar_url(event=event, thumbnail=thumbnail)


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
        from pretalx.common.image import (  # noqa: PLC0415 -- thin method
            THUMBNAIL_SIZES,
            queue_thumbnail_regeneration,
        )

        if not self.avatar_url:
            return ""
        if not thumbnail:
            image = self.avatar
        else:
            if thumbnail not in THUMBNAIL_SIZES:
                return None
            image = (
                self.avatar_thumbnail_tiny
                if thumbnail == "tiny"
                else self.avatar_thumbnail
            )
            if not image:
                queue_thumbnail_regeneration(self.avatar)
                image = self.avatar
        if event and event.custom_domain:
            return urljoin(event.custom_domain, image.url)
        return urljoin(settings.SITE_URL, image.url)
