# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.interfaces.validators.speaker import (
    validate_speakers_within_limit,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_speakers_within_limit_no_max_set_is_noop():
    event = EventFactory()
    assert event.cfp.max_speakers is None

    validate_speakers_within_limit(event, current=10, pending=10, additional=10)


def test_validate_speakers_within_limit_within_limit_passes():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 3
    event.cfp.save()

    validate_speakers_within_limit(event, current=1, pending=1, additional=1)


def test_validate_speakers_within_limit_at_limit_passes():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 3
    event.cfp.save()

    validate_speakers_within_limit(event, current=2, pending=0, additional=1)


def test_validate_speakers_within_limit_over_limit_raises():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 2
    event.cfp.save()

    with pytest.raises(ValidationError) as exc_info:
        validate_speakers_within_limit(event, current=1, pending=1, additional=1)

    assert "maximum" in exc_info.value.messages[0].lower()


def test_validate_speakers_within_limit_counts_pending_invitations():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 2
    event.cfp.save()

    with pytest.raises(ValidationError):
        validate_speakers_within_limit(event, current=1, pending=1, additional=1)
