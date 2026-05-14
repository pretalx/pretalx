# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import SubmissionType
from pretalx.submission.validators.type import validate_unique_submission_type_name
from tests.factories import EventFactory, SubmissionTypeFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_submission_type_name_accepts_unique_name():
    event = EventFactory()
    SubmissionTypeFactory(event=event, name="Keynote")

    validate_unique_submission_type_name(SubmissionType(event=event, name="Workshop"))


def test_validate_unique_submission_type_name_rejects_duplicate():
    existing = SubmissionTypeFactory(name="Keynote")

    with pytest.raises(ValidationError) as exc_info:
        validate_unique_submission_type_name(
            SubmissionType(event=existing.event, name="Keynote")
        )

    assert "name" in exc_info.value.message_dict


def test_validate_unique_submission_type_name_allows_self_on_update():
    existing = SubmissionTypeFactory(name="Keynote")

    validate_unique_submission_type_name(existing)


def test_validate_unique_submission_type_name_skips_when_event_or_name_missing():
    event = EventFactory()

    validate_unique_submission_type_name(SubmissionType(event=event, name=""))
    validate_unique_submission_type_name(SubmissionType(name="Keynote"))
