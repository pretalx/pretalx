# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.safelink import safelink

pytestmark = pytest.mark.unit


def test_safelink_produces_redirect_url():
    result = safelink("https://example.com")
    assert "redirect" in result
    assert "url=" in result
