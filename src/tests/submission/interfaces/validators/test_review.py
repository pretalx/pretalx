# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.interfaces.validators.review import (
    validate_non_independent_category_remains,
)
from tests.factories import EventFactory, ReviewScoreCategoryFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validator_raises_when_self_is_only_non_independent():
    """The category being validated is excluded from the count of remaining ones."""
    event = EventFactory()
    event.score_categories.all().delete()
    only = ReviewScoreCategoryFactory(event=event, is_independent=False)

    with pytest.raises(ValidationError):
        validate_non_independent_category_remains(only)


def test_validator_passes_when_another_non_independent_exists():
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    other = ReviewScoreCategoryFactory(event=event, is_independent=False)

    validate_non_independent_category_remains(other)
