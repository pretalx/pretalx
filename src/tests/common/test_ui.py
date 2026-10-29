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
    assert has_good_contrast(invalid_color) is True


def _compact(html):
    return " ".join(str(html).split())


def test_button_get_context():
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

    assert btn.get_context() == {
        "label": "Go",
        "color": "primary",
        "size": "sm",
        "icon": "arrow-right",
        "extra_classes": "ml-2",
        "name": "action",
        "value": "go",
        "type": "button",
        "id": "go-btn",
    }
    assert Button(label="Go").get_context() == {
        "label": "Go",
        "color": "success",
        "size": "",
        "icon": None,
        "extra_classes": "",
        "name": "",
        "value": "",
        "type": "submit",
        "id": None,
    }


def test_button_str_renders_html():
    btn = Button(label="Save it", color="primary", icon="check", name="save", value="1")

    assert _compact(btn) == (
        '<button type="submit" class="btn btn-primary" name="save" value="1" >'
        ' <i class="fa fa-check"></i> Save it </button>'
    )
    assert _compact(Button(label="Plain", icon=None)) == (
        '<button type="submit" class="btn btn-success" name="" value="" > Plain </button>'
    )


def test_link_button_renders_anchor():
    lb = LinkButton(href="/go", label="Go", color="info", icon="arrow-right")

    assert lb.get_context() == {
        "label": "Go",
        "color": "info",
        "size": "",
        "icon": "arrow-right",
        "extra_classes": "",
        "href": "/go",
        "disabled": "",
        "dialog": False,
    }
    assert _compact(lb) == (
        '<a class="btn btn-info" role="button" href="/go" >'
        ' <i class="fa fa-arrow-right"></i> Go </a>'
    )


def test_delete_link_renders_confirmed_danger_link():
    lb = delete_link("/remove")

    assert isinstance(lb, LinkButton)
    assert lb.href == "/remove"
    assert lb.color == "outline-danger"
    assert lb.label == phrases.base.delete_button
    assert lb.dialog is True
    assert _compact(lb) == (
        '<a class="btn btn-outline-danger" role="button" href="/remove"'
        " data-confirm-dialog > Delete </a>"
    )
    custom = delete_link("/remove", label="Remove", color="danger")
    assert (custom.label, custom.color) == ("Remove", "danger")


def test_delete_link_disabled_renders_explained_escaped_non_link():
    lb = delete_link("/remove", disabled='<script>"x"')

    assert lb.disabled == '<script>"x"'
    assert _compact(lb) == (
        '<a class="btn btn-outline-danger disabled" role="button"'
        ' aria-disabled="true" title="&lt;script&gt;&quot;x&quot;" > Delete </a>'
    )


def test_button_factories():
    btn = delete_button()
    assert isinstance(btn, Button)
    assert btn.color == "outline-danger"
    assert btn.label == phrases.base.delete_button

    lb = back_button("/previous")
    assert isinstance(lb, LinkButton)
    assert lb.href == "/previous"
    assert lb.color == "secondary"
    assert lb.label == phrases.base.back_button

    btn = send_button()
    assert isinstance(btn, Button)
    assert btn.label == phrases.base.send


def test_generate_contrast_color_clears_both_thresholds():
    light_bg = (1.0, 1.0, 1.0)
    dark_bg = (18 / 255, 20 / 255, 22 / 255)

    for seed in range(360):
        random.seed(seed)
        rgb = _hex_to_rgb_unit(generate_contrast_color())

        assert _contrast(rgb, light_bg) >= 2.5, seed
        assert _contrast(rgb, dark_bg) >= 2.5, seed


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


def test_generate_contrast_color_ignores_unparseable_and_greyscale_existing():
    random.seed(1)
    baseline = generate_contrast_color(existing_colors=[])
    random.seed(1)
    with_garbage = generate_contrast_color(
        existing_colors=["not-a-color", "#ggg", "", "#888888", "#000000", "#ffffff"]
    )

    assert with_garbage == baseline


def test_generate_contrast_color_falls_back_when_no_candidate_clears():
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

    assert all(isinstance(b, LinkButton) for b in buttons)
    assert [(b.href, b.color) for b in buttons] == [
        ("https://docs.pretalx.org/api/", "secondary"),
        (event.api_urls.base, "success"),
    ]
