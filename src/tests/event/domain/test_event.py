# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.event.domain.event import create_event
from pretalx.event.models import Event
from tests.factories import OrganiserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _common_fields():
    return {
        "name": "Test Event",
        "timezone": "UTC",
        "email": "test@example.com",
        "locale": "en",
        "date_from": dt.date(2025, 6, 10),
        "date_to": dt.date(2025, 6, 12),
    }


def test_create_event_lowercases_slug():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en"], slug="MixedCase", **_common_fields()
    )

    assert event.slug == "mixedcase"
    assert Event.objects.get(pk=event.pk).slug == "mixedcase"


def test_create_event_writes_locale_arrays():
    """``locales`` populates both locale_array and content_locale_array."""
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en", "de"], slug="evt", **_common_fields()
    )

    assert event.locale_array == "en,de"
    assert event.content_locale_array == "en,de"


def test_create_event_passes_through_extra_fields():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser,
        locales=["en"],
        slug="evt",
        primary_color="#ff0000",
        **_common_fields(),
    )

    assert event.primary_color == "#ff0000"
