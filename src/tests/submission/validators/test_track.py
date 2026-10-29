# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import Track
from pretalx.submission.validators.track import validate_unique_track_name
from tests.factories import EventFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_track_name():
    event = EventFactory()
    existing = TrackFactory(event=event, name="Backend")

    validate_unique_track_name(Track(event=event, name="Frontend"))
    validate_unique_track_name(Track(event=event, name=""))
    validate_unique_track_name(Track(name="Backend"))
    validate_unique_track_name(existing)
    with pytest.raises(ValidationError) as exc_info:
        validate_unique_track_name(Track(event=event, name="Backend"))

    assert exc_info.value.message_dict == {
        "name": ["You already have a track by this name!"]
    }
