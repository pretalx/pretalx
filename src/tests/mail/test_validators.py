# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from contextlib import nullcontext

import pytest
from django.core.exceptions import ValidationError

from pretalx.mail.validators import (
    validate_text_no_empty_links,
    validate_text_placeholders,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("text", "valid", "expectation"),
    (
        ("Hello {name}", {"name": object()}, nullcontext()),
        ("No placeholders here", {}, nullcontext()),
        ("", {}, nullcontext()),
        (
            "Hello {totally_invalid_placeholder}",
            {},
            pytest.raises(ValidationError, match="totally_invalid_placeholder"),
        ),
        (
            "Hello {unmatched",
            {},
            pytest.raises(ValidationError, match="Invalid email template"),
        ),
    ),
    ids=("known", "plain", "empty", "unknown", "malformed"),
)
def test_validate_text_placeholders(text, valid, expectation):
    with expectation:
        validate_text_placeholders(text, valid)


@pytest.mark.parametrize(
    ("text", "expectation"),
    (
        ("Visit [our site](https://example.com)", nullcontext()),
        ("", nullcontext()),
        ("[Click here]()", pytest.raises(ValidationError, match="empty link")),
    ),
    ids=("real_link", "empty_text", "empty_href"),
)
@pytest.mark.django_db
def test_validate_text_no_empty_links(text, expectation):
    event = EventFactory()
    with expectation:
        validate_text_no_empty_links(text, {}, event)
