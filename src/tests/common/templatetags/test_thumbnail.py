# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.thumbnail import thumbnail

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", (None, "not-a-field"))
def test_thumbnail_returns_none_for_invalid_input(value):
    """Invalid inputs (None, plain string) have no .url fallback, so None is returned."""
    assert thumbnail(value, "default") is None
