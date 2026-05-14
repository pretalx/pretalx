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


def test_biography_widget_with_suggestions():
    suggestions = [
        {"id": 1, "event_name": "PyCon", "biography": "I am a **Python** developer."},
        {"id": 2, "event_name": "JSConf", "biography": "I do JavaScript too."},
    ]
    widget = BiographyWidget(suggestions=suggestions)

    ctx = widget.get_context("biography", "", {})

    assert len(ctx["suggestions"]) == 2
    assert ctx["suggestions"][0]["event_name"] == "PyCon"
    assert ctx["suggestions"][0]["id"] == "1"
    assert "biography" not in ctx["suggestions"][0]
    assert "Python" in ctx["suggestions"][0]["preview"]
    assert "**" not in ctx["suggestions"][0]["preview"]
    assert ctx["biographies"]["1"] == "I am a **Python** developer."
    assert ctx["biographies"]["2"] == "I do JavaScript too."


def test_biography_widget_truncates_long_preview():
    long_bio = "A" * 300
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": long_bio}]
    )

    ctx = widget.get_context("biography", "", {})

    preview = ctx["suggestions"][0]["preview"]
    assert len(preview) == 201
    assert preview.endswith("…")


def test_biography_widget_no_ellipsis_for_short_preview():
    short_bio = "Short bio."
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": short_bio}]
    )

    ctx = widget.get_context("biography", "", {})

    assert "…" not in ctx["suggestions"][0]["preview"]
