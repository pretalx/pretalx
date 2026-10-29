# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.exceptions import ValidationError

from pretalx.person.validators import validate_email_unique
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_email_unique_ignores_case_and_excludes_only_the_given_user():
    UserFactory(email="taken@example.com")
    user = UserFactory(email="me@example.com")

    validate_email_unique("free@example.com")
    validate_email_unique("me@example.com", exclude_user=user)
    with pytest.raises(ValidationError):
        validate_email_unique("TAKEN@example.com")
    with pytest.raises(ValidationError):
        validate_email_unique("taken@example.com", exclude_user=user)
    with pytest.raises(ValidationError):
        validate_email_unique("me@example.com")
