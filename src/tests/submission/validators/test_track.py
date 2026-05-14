# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import Track
from pretalx.submission.validators.track import validate_unique_track_name
from tests.factories import EventFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_track_name_accepts_unique_name():
    event = EventFactory()
    TrackFactory(event=event, name="Backend")

    validate_unique_track_name(Track(event=event, name="Frontend"))


def test_validate_unique_track_name_rejects_duplicate():
    existing = TrackFactory(name="Backend")

    with pytest.raises(ValidationError) as exc_info:
        validate_unique_track_name(Track(event=existing.event, name="Backend"))

    assert "name" in exc_info.value.message_dict


def test_validate_unique_track_name_allows_self_on_update():
    existing = TrackFactory(name="Backend")

    validate_unique_track_name(existing)


def test_validate_unique_track_name_skips_when_event_or_name_missing():
    event = EventFactory()

    validate_unique_track_name(Track(event=event, name=""))
    validate_unique_track_name(Track(name="Backend"))
