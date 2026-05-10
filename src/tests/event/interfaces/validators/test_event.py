# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.event.interfaces.validators.event import validate_event_slug_unique
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_event_slug_unique_raises_on_duplicate():
    EventFactory(slug="dupe")

    with pytest.raises(ValidationError) as exc_info:
        validate_event_slug_unique("dupe")

    assert "slug" in exc_info.value.message_dict


def test_validate_event_slug_unique_case_insensitive():
    EventFactory(slug="myevent")

    with pytest.raises(ValidationError):
        validate_event_slug_unique("MyEvent")


def test_validate_event_slug_unique_allows_same_instance():
    event = EventFactory(slug="myevent")

    validate_event_slug_unique("myevent", exclude_event=event)


@pytest.mark.parametrize("slug", ("", None), ids=("empty", "none"))
def test_validate_event_slug_unique_returns_early_for_falsy(slug):
    validate_event_slug_unique(slug)
