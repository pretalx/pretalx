# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.common.models import ActivityLog
from pretalx.person.models import User


class UserSerializer(PretalxSerializer):
    class Meta:
        model = User
        fields = ("code", "name")


@register_serializer(versions=CURRENT_VERSIONS)
class ActivityLogSerializer(PretalxSerializer):
    person = UserSerializer()

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "timestamp",
            "action_type",
            "is_orga_action",
            "person",
            "display",
            "data",
        ]
