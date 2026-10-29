# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from tests.factories import TagFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_tag_str_and_log_parent():
    tag = TagFactory(tag="keynote")

    assert str(tag) == "keynote"
    assert tag.log_parent == tag.event
