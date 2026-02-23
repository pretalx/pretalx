# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.ui import has_good_contrast


@pytest.mark.parametrize(
    ("color", "expected"),
    (
        # Dark colors - should have good contrast with white text
        ("#000000", True),  # Black - 21:1 contrast
        ("#1a1a1a", True),  # Very dark grey
        ("#0000ff", True),  # Blue - 8.59:1 contrast
        ("#800000", True),  # Maroon
        ("#800080", True),  # Purple
        # Medium colors - may or may not pass depending on exact shade
        ("#3aa57c", False),  # pretalx green - ~2.99:1, doesn't pass 4.5
        ("#008000", True),  # Dark green - 5.14:1, passes
        # Light colors - should NOT have good contrast with white text
        ("#ffffff", False),  # White
        ("#ffff00", False),  # Yellow
        ("#00ffff", False),  # Cyan
        ("#f0f0f0", False),  # Light grey
        ("#ffcc00", False),  # Gold/amber
        ("#90ee90", False),  # Light green
        ("#add8e6", False),  # Light blue
        # Edge cases around the 4.5 threshold
        ("#767676", True),  # Just passes WCAG AA (4.54:1)
        ("#777777", False),  # Just fails WCAG AA (4.48:1)
    ),
)
def test_has_good_contrast(color, expected):
    assert has_good_contrast(color) == expected


@pytest.mark.parametrize(
    ("color", "threshold", "expected"),
    (
        ("#767676", 4.5, True),  # Passes at 4.5
        ("#767676", 4.6, False),  # Fails at higher threshold
        ("#ffffff", 1.0, True),  # White passes very low threshold
        ("#000000", 21.0, True),  # Black passes even highest threshold
    ),
)
def test_has_good_contrast_custom_threshold(color, threshold, expected):
    assert has_good_contrast(color, threshold=threshold) == expected


@pytest.mark.parametrize("invalid_color", ("not-a-color", "#gggggg", "rgb(0,0,0)", ""))
def test_has_good_contrast_invalid_input_returns_true(invalid_color):
    # Invalid colors should return True (assume good contrast) to avoid
    # breaking the UI - the default pretalx color has good contrast
    assert has_good_contrast(invalid_color) is True
