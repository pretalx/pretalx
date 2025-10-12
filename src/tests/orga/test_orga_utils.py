# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.conf import settings

from pretalx.orga.utils.i18n import get_moment_locale


@pytest.mark.parametrize(
    "locale,expected",
    (
        ("af", "af"),
        ("hy-am", "hy-am"),
        ("de-DE", "de"),
        ("de_DE", "de"),
        ("ja_JP", "ja"),
        ("delol_DE", settings.LANGUAGE_CODE),
    ),
)
def test_get_moment_locale(locale, expected):
    assert get_moment_locale(locale) == expected
