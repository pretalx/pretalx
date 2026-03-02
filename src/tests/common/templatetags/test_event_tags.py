# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.event_tags import get_feature_flag
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_get_feature_flag_default():
    event = EventFactory()
    assert get_feature_flag(event, "show_schedule") is True


def test_get_feature_flag_custom_flag():
    event = EventFactory(feature_flags={"custom_flag": True})
    assert get_feature_flag(event, "custom_flag") is True


def test_get_feature_flag_missing_returns_false():
    event = EventFactory()
    assert get_feature_flag(event, "nonexistent_flag") is False
