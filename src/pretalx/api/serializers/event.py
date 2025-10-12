# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from rest_framework.serializers import ModelSerializer

from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.versions import register_serializer
from pretalx.event.models import Event


@register_serializer()
class EventListSerializer(ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "name",
            "slug",
            "is_public",
            "date_from",
            "date_to",
            "timezone",
        ]

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
    logo = UploadedFileField(required=False)

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + [
            "email",  # Email is public in the footer anyway
            "primary_color",
            "custom_domain",
            "logo",
            "header_image",
            "locale",
            "locales",
            "content_locales",
        ]
