# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.text.phrases import phrases
from pretalx.common.ui import (
    Button,
    LinkButton,
    _channel_luminance,
    api_buttons,
    back_button,
    delete_button,
    delete_link,
    has_good_contrast,
    send_button,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0.0, 0.0),
        (0.03928, 0.03928 / 12.92),
        (0.04, ((0.04 + 0.055) / 1.055) ** 2.4),
        (1.0, 1.0),
    ),
)
def test_channel_luminance(value, expected):
    assert _channel_luminance(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("color", "expected"),
    (
        ("#000000", True),
        ("#1a1a1a", True),
        ("#0000ff", True),
        ("#800000", True),
        ("#800080", True),
        ("#3aa57c", False),
        ("#008000", True),
        ("#ffffff", False),
        ("#ffff00", False),
        ("#00ffff", False),
        ("#f0f0f0", False),
        ("#ffcc00", False),
        ("#90ee90", False),
        ("#add8e6", False),
        ("#767676", True),
        ("#777777", False),
    ),
)
def test_has_good_contrast(color, expected):
    assert has_good_contrast(color) == expected


@pytest.mark.parametrize(
    ("color", "threshold", "expected"),
    (
        ("#767676", 4.5, True),
        ("#767676", 4.6, False),
        ("#ffffff", 1.0, True),
        ("#000000", 21.0, True),
    ),
)
def test_has_good_contrast_custom_threshold(color, threshold, expected):
    assert has_good_contrast(color, threshold=threshold) == expected


@pytest.mark.parametrize("invalid_color", ("not-a-color", "#gggggg", "rgb(0,0,0)", ""))
def test_has_good_contrast_invalid_input_returns_true(invalid_color):
    """Invalid colours fall back to True because the default pretalx colour
    has good contrast with white, and swapping button colours on a parse
    error would be worse."""
    assert has_good_contrast(invalid_color) is True


def test_button_defaults():
    btn = Button()

    assert btn.label == phrases.base.save
    assert btn.color == "success"
    assert btn.size == "lg"
    assert btn.icon == "check"
    assert btn.type == "submit"
    assert btn.name == ""
    assert btn.value == ""
    assert btn.extra_classes == ""
    assert btn.id is None


def test_button_custom_values():
    btn = Button(
        label="Go",
        color="primary",
        size="sm",
        icon="arrow-right",
        extra_classes="ml-2",
        name="action",
        value="go",
        _type="button",
        _id="go-btn",
    )

    assert btn.label == "Go"
    assert btn.color == "primary"
    assert btn.size == "sm"
    assert btn.icon == "arrow-right"
    assert btn.extra_classes == "ml-2"
    assert btn.name == "action"
    assert btn.value == "go"
    assert btn.type == "button"
    assert btn.id == "go-btn"


def test_button_icon_none_disables_icon():
    """Passing icon=None explicitly should suppress the icon entirely."""
    btn = Button(icon=None)
    assert btn.icon is None


def test_button_get_context():
    btn = Button(label="Go", color="info", name="x", value="y", _id="myid")
    ctx = btn.get_context()

    assert ctx == {
        "label": "Go",
        "color": "info",
        "size": "lg",
        "icon": "check",
        "extra_classes": "",
        "name": "x",
        "value": "y",
        "type": "submit",
        "id": "myid",
    }


def test_button_str_renders_html():
    btn = Button(label="Save it", color="primary", icon="check", name="save", value="1")
    html = str(btn)

    assert "btn-primary" in html
    assert "btn-lg" in html
    assert "Save it" in html
    assert "fa-check" in html
    assert 'name="save"' in html
    assert 'value="1"' in html


def test_button_str_without_icon():
    btn = Button(label="Plain", icon=None)
    html = str(btn)

    assert "fa-" not in html
    assert "Plain" in html


def test_link_button_defaults():
    lb = LinkButton(href="/somewhere")

    assert lb.href == "/somewhere"
    assert lb.icon is None
    assert lb.color == "success"
    assert lb.size == "lg"


def test_link_button_custom_values():
    lb = LinkButton(href="/go", label="Go", color="warning", size="sm", icon="link")

    assert lb.href == "/go"
    assert lb.label == "Go"
    assert lb.color == "warning"
    assert lb.size == "sm"
    assert lb.icon == "link"


def test_link_button_get_context():
    lb = LinkButton(href="/test", label="Click", color="info", icon="star")
    ctx = lb.get_context()

    assert ctx == {
        "label": "Click",
        "color": "info",
        "size": "lg",
        "icon": "star",
        "extra_classes": "",
        "href": "/test",
    }


def test_link_button_str_renders_anchor():
    lb = LinkButton(href="/go", label="Go", color="info", icon="arrow-right")
    html = str(lb)

    assert 'href="/go"' in html
    assert "btn-info" in html
    assert "Go" in html
    assert "fa-arrow-right" in html
    assert "<button" not in html


def test_delete_link_defaults():
    lb = delete_link("/remove")

    assert isinstance(lb, LinkButton)
    assert lb.href == "/remove"
    assert lb.color == "outline-danger"
    assert lb.icon == "trash"
    assert lb.label == phrases.base.delete_button


def test_delete_link_custom_label_and_color():
    lb = delete_link("/remove", label="Remove", color="danger")

    assert lb.label == "Remove"
    assert lb.color == "danger"


def test_delete_button_returns_danger_button():
    btn = delete_button()

    assert isinstance(btn, Button)
    assert btn.color == "danger"
    assert btn.icon == "trash"
    assert btn.label == phrases.base.delete_button


def test_back_button_returns_outline_info_link():
    lb = back_button("/previous")

    assert isinstance(lb, LinkButton)
    assert lb.href == "/previous"
    assert lb.color == "outline-info"
    assert lb.icon is None
    assert lb.label == phrases.base.back_button


def test_send_button_returns_envelope_button():
    btn = send_button()

    assert isinstance(btn, Button)
    assert btn.icon == "envelope"
    assert btn.label == phrases.base.send


@pytest.mark.django_db
def test_api_buttons_returns_docs_and_api_links(event):
    buttons = api_buttons(event)

    assert len(buttons) == 2
    assert all(isinstance(b, LinkButton) for b in buttons)
    assert buttons[0].href == "https://docs.pretalx.org/api/"
    assert buttons[0].color == "info"
    assert buttons[0].icon == "book"
    assert buttons[1].href == event.api_urls.base
