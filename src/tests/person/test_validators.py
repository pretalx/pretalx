# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.exceptions import ValidationError

from pretalx.person.validators import validate_email_unique
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("input_email", ("taken@example.com", "TAKEN@example.com"))
def test_validate_email_unique_rejects_duplicate(input_email):
    UserFactory(email="taken@example.com")

    with pytest.raises(ValidationError):
        validate_email_unique(input_email)


def test_validate_email_unique_passes_for_unused_email():
    validate_email_unique("free@example.com")


def test_validate_email_unique_excludes_given_user():
    """exclude_user lets a user keep their own email through edits."""
    user = UserFactory(email="me@example.com")

    validate_email_unique("me@example.com", exclude_user=user)


def test_validate_email_unique_still_rejects_other_users_email_when_excluding():
    UserFactory(email="taken@example.com")
    user = UserFactory(email="me@example.com")

    with pytest.raises(ValidationError):
        validate_email_unique("taken@example.com", exclude_user=user)
