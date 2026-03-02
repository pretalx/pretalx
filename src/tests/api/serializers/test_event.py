# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.serializers.event import EventListSerializer, EventSerializer
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_list_serializer_data():
    event = EventFactory()
    data = EventListSerializer(event).data
    assert data == {
        "name": {"en": event.name},
        "slug": event.slug,
        "is_public": event.is_public,
        "date_from": event.date_from.isoformat(),
        "date_to": event.date_to.isoformat(),
        "timezone": event.timezone,
    }


def test_event_serializer_data():
    event = EventFactory()
    data = EventSerializer(event).data
    assert data == {
        "name": {"en": event.name},
        "slug": event.slug,
        "is_public": event.is_public,
        "date_from": event.date_from.isoformat(),
        "date_to": event.date_to.isoformat(),
        "timezone": event.timezone,
        "email": event.email,
        "primary_color": event.primary_color,
        "custom_domain": event.custom_domain,
        "logo": None,
        "header_image": None,
        "og_image": None,
        "locale": event.locale,
        "locales": event.locales,
        "content_locales": event.content_locales,
    }
