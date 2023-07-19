# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

from rest_framework.serializers import ModelSerializer
from urlman.serializers import UrlManField

from pretalx.event.models import Event


class EventSerializer(ModelSerializer):
    urls = UrlManField(urls=["base", "schedule", "login", "feed"])

    class Meta:
        model = Event
        fields = (
            "name",
            "slug",
            "is_public",
            "date_from",
            "date_to",
            "timezone",
            "urls",
        )
