# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import SubmissionType
from pretalx.submission.validators.type import validate_unique_submission_type_name
from tests.factories import EventFactory, SubmissionTypeFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_submission_type_name():
    event = EventFactory()
    existing = SubmissionTypeFactory(event=event, name="Keynote")

    validate_unique_submission_type_name(SubmissionType(event=event, name="Workshop"))
    validate_unique_submission_type_name(SubmissionType(event=event, name=""))
    validate_unique_submission_type_name(SubmissionType(name="Keynote"))
    validate_unique_submission_type_name(existing)
    with pytest.raises(ValidationError) as exc_info:
        validate_unique_submission_type_name(
            SubmissionType(event=event, name="Keynote")
        )

    assert exc_info.value.message_dict == {
        "name": ["You already have a session type by this name!"]
    }
