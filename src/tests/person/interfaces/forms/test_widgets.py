# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.forms.widgets import MarkdownWidget
from pretalx.person.interfaces.forms.widgets import BiographyWidget

pytestmark = pytest.mark.unit


def test_biography_widget_without_suggestions():
    widget = BiographyWidget()

    ctx = widget.get_context("biography", "", {})

    assert ctx["suggestions"] == []
    assert ctx["biographies"] == {}
    assert isinstance(widget, MarkdownWidget)


def test_biography_widget_with_suggestions_renders_truncated_previews():
    long_bio = "A" * 300
    suggestions = [
        {"id": 1, "event_name": "PyCon", "biography": "I am a **Python** developer."},
        {"id": 2, "event_name": "JSConf", "biography": long_bio},
    ]
    widget = BiographyWidget(suggestions=suggestions)

    ctx = widget.get_context("biography", "", {})

    assert ctx["suggestions"] == [
        {"id": "1", "event_name": "PyCon", "preview": "I am a Python developer."},
        {"id": "2", "event_name": "JSConf", "preview": "A" * 200 + "…"},
    ]
    assert ctx["biographies"] == {"1": "I am a **Python** developer.", "2": long_bio}
