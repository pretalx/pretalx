# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.phrases import phrase

pytestmark = pytest.mark.unit


def test_phrase_formats_kwargs():
    assert str(phrase("phrases.base.save")) == "Save"
    assert "Europe/Berlin" in str(
        phrase("phrases.schedule.timezone_hint", tz="Europe/Berlin")
    )
