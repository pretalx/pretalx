# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.models import Tag
from pretalx.submission.validators.tag import validate_unique_tag
from tests.factories import EventFactory, TagFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_tag():
    event = EventFactory()
    existing = TagFactory(event=event, tag="python")

    validate_unique_tag(Tag(event=event, tag="django"))
    validate_unique_tag(Tag(event=event, tag=""))
    validate_unique_tag(Tag(tag="python"))
    validate_unique_tag(existing)
    with pytest.raises(ValidationError) as exc_info:
        validate_unique_tag(Tag(event=event, tag="Python"))

    assert exc_info.value.message_dict == {
        "tag": ["You already have a tag by this name!"]
    }
