# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework.serializers import HiddenField, UUIDField

from pretalx.api.serializers.availability import (
    AvailabilitySerializer,
    replace_from_serializer_data,
)
from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.schedule.models import Room


@register_serializer(versions=CURRENT_VERSIONS)
class RoomSerializer(PretalxSerializer):
    uuid = UUIDField(
        help_text="The uuid field is equal the the guid field if a guid has been set. Otherwise, it will contain a computed (stable) UUID.",
        read_only=True,
    )

    class Meta:
        model = Room
        fields = ("id", "name", "description", "uuid", "guid", "capacity", "position")


@register_serializer(versions=CURRENT_VERSIONS)
class RoomOrgaSerializer(RoomSerializer):
    event = HiddenField(default=CurrentEventDefault())
    availabilities = AvailabilitySerializer(many=True, required=False)

    def create(self, validated_data):
        availabilities_data = validated_data.pop("availabilities", None)
        room = super().create(validated_data)
        if availabilities_data is not None:
            replace_from_serializer_data(
                event=self.event, instance=room, availabilities_data=availabilities_data
            )
        return room

    def update(self, instance, validated_data):
        availabilities_data = validated_data.pop("availabilities", None)
        room = super().update(instance, validated_data)
        if availabilities_data is not None:
            replace_from_serializer_data(
                event=self.event, instance=room, availabilities_data=availabilities_data
            )
        return room

    class Meta:
        model = Room
        fields = (
            *RoomSerializer.Meta.fields,
            "speaker_info",
            "availabilities",
            "event",
        )
