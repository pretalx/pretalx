# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.phrases import phrase

pytestmark = pytest.mark.unit


def test_phrase_without_kwargs():
    result = phrase("phrases.base.save")
    assert str(result) == "Save"


def test_phrase_with_kwargs():
    """Phrase with %-formatting substitutes kwargs."""
    result = phrase("phrases.schedule.timezone_hint", tz="Europe/Berlin")
    assert "Europe/Berlin" in str(result)
