# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework.serializers import BooleanField, ModelSerializer

from pretalx.schedule.domain.availability import replace_availabilities
from pretalx.schedule.models import Availability


class AvailabilitySerializer(ModelSerializer):
    allDay = BooleanField(
        help_text="Computed field indicating if an availability fills an entire day.",
        read_only=True,
        source="all_day",
    )

    class Meta:
        model = Availability
        fields = ("start", "end", "allDay")


def replace_from_serializer_data(*, event, instance, availabilities_data):
    availabilities = [
        Availability(event=event, start=item["start"], end=item["end"])
        for item in availabilities_data
    ]
    replace_availabilities(instance, availabilities)
