# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.mail.validators import (
    validate_text_no_empty_links,
    validate_text_placeholders,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit]


def test_validate_text_placeholders_accepts_known():
    validate_text_placeholders("Hello {name}", {"name": object()})


def test_validate_text_placeholders_accepts_plain_text():
    validate_text_placeholders("No placeholders here", {})


def test_validate_text_placeholders_accepts_empty_text():
    validate_text_placeholders("", {})


def test_validate_text_placeholders_rejects_unknown():
    with pytest.raises(ValidationError, match="totally_invalid_placeholder"):
        validate_text_placeholders("Hello {totally_invalid_placeholder}", {})


def test_validate_text_placeholders_rejects_malformed_braces():
    with pytest.raises(ValidationError, match="Invalid email template"):
        validate_text_placeholders("Hello {unmatched", {})


@pytest.mark.django_db
def test_validate_text_no_empty_links_accepts_real_link():
    event = EventFactory()
    validate_text_no_empty_links("Visit [our site](https://example.com)", {}, event)


@pytest.mark.django_db
def test_validate_text_no_empty_links_rejects_empty_href():
    event = EventFactory()
    with pytest.raises(ValidationError, match="empty link"):
        validate_text_no_empty_links("[Click here]()", {}, event)


@pytest.mark.django_db
def test_validate_text_no_empty_links_accepts_empty_text():
    event = EventFactory()
    validate_text_no_empty_links("", {}, event)
