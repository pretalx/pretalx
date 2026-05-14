# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import Tag
from pretalx.submission.validators.tag import validate_unique_tag
from tests.factories import EventFactory, TagFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_tag_accepts_unique_name():
    event = EventFactory()
    TagFactory(event=event, tag="python")

    validate_unique_tag(Tag(event=event, tag="django"))


def test_validate_unique_tag_rejects_duplicate():
    existing = TagFactory(tag="python")

    with pytest.raises(ValidationError) as exc_info:
        validate_unique_tag(Tag(event=existing.event, tag="python"))

    assert "tag" in exc_info.value.message_dict


def test_validate_unique_tag_allows_self_on_update():
    existing = TagFactory(tag="python")

    validate_unique_tag(existing)


def test_validate_unique_tag_skips_when_event_or_tag_missing():
    event = EventFactory()

    validate_unique_tag(Tag(event=event, tag=""))
    validate_unique_tag(Tag(tag="python"))
