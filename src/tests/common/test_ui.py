# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import colorsys
import random

import pytest

from pretalx.common.text.phrases import phrases
from pretalx.common.ui import (
    Button,
    LinkButton,
    _channel_luminance,
    _relative_luminance,
    api_buttons,
    back_button,
    delete_button,
    delete_link,
    generate_contrast_color,
    has_good_contrast,
    send_button,
)

pytestmark = pytest.mark.unit


def _hex_to_rgb_unit(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _contrast(rgb_a, rgb_b):
    la = _relative_luminance(*rgb_a) + 0.05
    lb = _relative_luminance(*rgb_b) + 0.05
    return max(la, lb) / min(la, lb)


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
        "disabled": "",
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


def test_delete_link_disabled_renders_explained_non_link():
    lb = delete_link("/remove", disabled="Cannot delete the last one")
    html = str(lb)

    assert lb.disabled == "Cannot delete the last one"
    assert 'aria-disabled="true"' in html
    assert 'title="Cannot delete the last one"' in html
    assert " disabled" in html
    assert 'href="/remove"' not in html


def test_delete_link_disabled_reason_is_html_escaped():
    lb = delete_link("/remove", disabled='<script>"x"')
    html = str(lb)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_delete_link_not_disabled_renders_normal_link():
    lb = delete_link("/remove")
    html = str(lb)

    assert 'href="/remove"' in html
    assert 'aria-disabled="true"' not in html


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


@pytest.mark.parametrize("seed", list(range(360)))
def test_generate_contrast_color_clears_both_thresholds(seed):
    random.seed(seed)
    color = generate_contrast_color()

    light_bg = (1.0, 1.0, 1.0)
    dark_bg = (18 / 255, 20 / 255, 22 / 255)
    rgb = _hex_to_rgb_unit(color)

    assert _contrast(rgb, light_bg) >= 2.5
    assert _contrast(rgb, dark_bg) >= 2.5


def test_generate_contrast_color_avoids_existing_hue():
    random.seed(0)
    base = generate_contrast_color()
    random.seed(0)
    other = generate_contrast_color(existing_colors=[base])

    base_hue = colorsys.rgb_to_hls(*_hex_to_rgb_unit(base))[0]
    other_hue = colorsys.rgb_to_hls(*_hex_to_rgb_unit(other))[0]
    diff = abs(base_hue - other_hue)
    circular = min(diff, 1 - diff)

    assert circular >= 30 / 360


def test_generate_contrast_color_ignores_unparseable_existing():
    random.seed(1)
    baseline = generate_contrast_color(existing_colors=[])
    random.seed(1)
    with_garbage = generate_contrast_color(existing_colors=["not-a-color", "#ggg", ""])

    assert with_garbage == baseline


def test_generate_contrast_color_ignores_greyscale_existing():
    """Greyscale colours have no meaningful hue, so they don't constrain
    the hue-separation search."""
    random.seed(2)
    baseline = generate_contrast_color(existing_colors=[])
    random.seed(2)
    with_grey = generate_contrast_color(
        existing_colors=["#888888", "#000000", "#ffffff"]
    )

    assert with_grey == baseline


def test_generate_contrast_color_falls_back_when_no_candidate_clears():
    """With 12 existing hues evenly distributed around the wheel, every
    possible hue is within 15° of one — so no candidate can ever clear the
    30° threshold and the function must return a colliding hue from the
    fallback path."""
    existing = []
    for i in range(12):
        r, g, b = colorsys.hls_to_rgb(i / 12, 0.5, 1.0)
        existing.append(
            f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
        )

    random.seed(0)
    color = generate_contrast_color(existing_colors=existing)

    result_hue = colorsys.rgb_to_hls(*_hex_to_rgb_unit(color))[0]
    min_dist = min(
        min(abs(result_hue - i / 12), 1 - abs(result_hue - i / 12)) for i in range(12)
    )
    assert min_dist < 30 / 360


@pytest.mark.django_db
def test_api_buttons_returns_docs_and_api_links(event):
    buttons = api_buttons(event)

    assert len(buttons) == 2
    assert all(isinstance(b, LinkButton) for b in buttons)
    assert buttons[0].href == "https://docs.pretalx.org/api/"
    assert buttons[0].color == "info"
    assert buttons[0].icon == "book"
    assert buttons[1].href == event.api_urls.base
