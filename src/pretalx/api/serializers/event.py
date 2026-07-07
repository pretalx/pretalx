# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from rest_framework.serializers import CharField, ListField, ModelSerializer

from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.versions import register_serializer
from pretalx.common.files import IMAGE_UPLOAD_TYPES
from pretalx.event.models import Event


@register_serializer()
class EventListSerializer(ModelSerializer):
    class Meta:
        model = Event
        fields = ["name", "slug", "is_public", "date_from", "date_to", "timezone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        with suppress(Exception):
            if not request or not request.user or not request.user.is_authenticated:
                # Keep API docs small; doesn’t matter for validation with unauthenticated
                # users.
                self.fields["timezone"].choices = []


@register_serializer()
class EventSerializer(EventListSerializer):
    locales = ListField(
        child=CharField(),
        read_only=True,
        help_text="Is a list of active event locales.",
    )
    content_locales = ListField(
        child=CharField(),
        read_only=True,
        help_text="Is a list of active content locales.",
    )
    logo = UploadedFileField(required=False, allowed_types=IMAGE_UPLOAD_TYPES)
    header_image = UploadedFileField(required=False, allowed_types=IMAGE_UPLOAD_TYPES)
    og_image = UploadedFileField(required=False, allowed_types=IMAGE_UPLOAD_TYPES)

    class Meta(EventListSerializer.Meta):
        fields = [
            *EventListSerializer.Meta.fields,
            "email",  # Email is public in the footer anyway
            "primary_color",
            "custom_domain",
            "logo",
            "header_image",
            "og_image",
            "locale",
            "locales",
            "content_locales",
        ]
