# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import uuid

from django.db import models
from django.utils.crypto import get_random_string

from pretalx.common.models.managers import PretalxManager
from pretalx.common.models.mixins import FileCleanupMixin


def cachedfile_name(instance, filename: str) -> str:
    secret = get_random_string(length=12)
    ext = filename.rsplit(".", maxsplit=1)[-1]
    return f"cachedfiles/{instance.id}.{secret}.{ext}"


class CachedFile(FileCleanupMixin, models.Model):
    """
    An uploaded file, primarily used for API uploads. Deleted after expiry.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    expires = models.DateTimeField()
    timestamp = models.DateTimeField(null=True, blank=True)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    # Possible formats: "api-upload-<token>" and "<session key>!<salt>"
    session_key = models.TextField(null=True, blank=True)
    file = models.FileField(
        null=True, blank=True, upload_to=cachedfile_name, max_length=255
    )

    objects = PretalxManager()

    class Meta:
        indexes = [models.Index(fields=["expires"])]

    def __str__(self):
        return f"CachedFile(id={self.id}, file={self.file})"

    @staticmethod
    def session_key_for_request(request, salt):
        if key := request.session.session_key:
            return f"{key}!{salt}"

    def bind_to_session(self, request, salt):
        """Restrict this file to the request's session. The salt adds namespacing
        to a view to prevent cross-view access."""
        self.session_key = self.session_key_for_request(request, salt)

    def allowed_for_session(self, request, salt):
        return bool(self.session_key) and (
            self.session_key == self.session_key_for_request(request, salt)
        )

    @staticmethod
    def build_absolute_url(file_field, request):
        """Return an absolute URL for a FileField value, or None if unavailable."""
        if not file_field:
            return None
        try:
            url = file_field.url
        except (AttributeError, ValueError):
            return None
        if request is None:
            return None
        return request.build_absolute_uri(url)
