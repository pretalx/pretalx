# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.event_tags import get_feature_flag
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("kwargs", "flag", "expected"),
    (
        ({}, "show_schedule", True),
        ({"feature_flags": {"custom_flag": True}}, "custom_flag", True),
        ({}, "nonexistent_flag", False),
    ),
    ids=("default", "custom", "missing"),
)
def test_get_feature_flag(kwargs, flag, expected):
    assert get_feature_flag(EventFactory(**kwargs), flag) is expected
