# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import colorsys
import random

from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases


class Button:
    color = "success"
    extra_classes = ""
    icon = "check"
    size = "lg"
    label = phrases.base.save
    _type = "submit"
    template_name = "common/ui/button.html"

    def __init__(
        self,
        *,
        label="",
        color="",
        size="",
        icon="",
        extra_classes="",
        name="",
        value="",
        _type="",
        _id=None,
    ):
        self.label = label or self.label
        self.name = name
        self.value = value
        self.color = color or self.color
        self.size = size or self.size
        self.icon = icon or (self.icon if icon is not None else None)
        self.extra_classes = extra_classes
        self.type = _type or self._type
        self.id = _id
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "name",
            "value",
            "type",
            "id",
        )

    def __str__(self):
        return get_template(self.template_name).render(self.get_context())

    def get_context(self):
        return {attr: getattr(self, attr) for attr in self.template_context}


class LinkButton(Button):
    href = ""
    template_name = "common/ui/linkbutton.html"

    def __init__(self, *, href="", icon=None, disabled="", **kwargs):
        self.href = href
        # A non-empty ``disabled`` is a human-readable reason why the action
        # is unavailable; it renders a non-clickable, explained hint.
        self.disabled = disabled
        super().__init__(icon=icon, **kwargs)
        self.template_context = (
            "label",
            "color",
            "size",
            "icon",
            "extra_classes",
            "href",
            "disabled",
        )


def delete_link(href, label=None, color=None, disabled=""):
    return LinkButton(
        href=href,
        label=label or phrases.base.delete_button,
        color=color or "outline-danger",
        icon="trash",
        disabled=disabled,
    )


def delete_button(label=None, color=None):
    return Button(color="danger", icon="trash", label=phrases.base.delete_button)


def back_button(href):
    return LinkButton(
        href=href, icon=None, label=phrases.base.back_button, color="outline-info"
    )


def send_button():
    return Button(icon="envelope", label=phrases.base.send)


def api_buttons(event):
    return [
        LinkButton(
            href="https://docs.pretalx.org/api/",
            color="info",
            icon="book",
            label=_("Documentation"),
        ),
        LinkButton(href=event.api_urls.base, label=_("Go to API")),
    ]


def _channel_luminance(c):
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(r, g, b):
    return (
        0.2126 * _channel_luminance(r)
        + 0.7152 * _channel_luminance(g)
        + 0.0722 * _channel_luminance(b)
    )


def has_good_contrast(color, threshold=4.5):
    """
    Calculates the colour contrast ratio to white using the WCAG formula.
    Thresholds: 4.5 for text, 3 for large text / graphical objects.

    https://www.w3.org/WAI/GL/wiki/Contrast_ratio
    """
    hex_color = color.lstrip("#")

    try:
        r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        # Returning False on error would lead to swapped button colours,
        # and as with an invalid colour, the default pretalx colour is used,
        # which has good contrast to white (the default case in this project's
        # context), we assume a good outcome on error.
        return True

    contrast_with_white = (1 + 0.05) / (_relative_luminance(r, g, b) + 0.05)
    return contrast_with_white >= threshold


def _lightness_for_luminance(hue, saturation, target):
    """Search the HSL lightness matching the luminance for the given hue.

    Our 10 bisection steps find a value within 1e-3."""
    lo, hi = 0.0, 1.0
    for _step in range(10):
        mid = (lo + hi) / 2
        r, g, b = colorsys.hls_to_rgb(hue, mid, saturation)
        if _relative_luminance(r, g, b) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _hex_to_hue(hex_color):
    from PIL import ImageColor

    try:
        r, g, b = (c / 255 for c in ImageColor.getrgb(hex_color)[:3])
    except ValueError:
        return None
    if max(r, g, b) == min(r, g, b):
        return None
    hue, _l, _s = colorsys.rgb_to_hls(r, g, b)
    return hue


def _hue_min_distance(hue, used_hues):
    return min(min(abs(hue - u), 1 - abs(hue - u)) for u in used_hues)


def generate_contrast_color(existing_colors=()):
    """Return a hex rgb colour with good backgroun contrast and a hue at
    least 30° away from any colour in ``existing_colors`` (if possible)."""
    used_hues = [
        hue
        for hue in (_hex_to_hue(color) for color in existing_colors)
        if hue is not None
    ]
    saturation = 0.65
    hue_separation = 30 / 360

    hue = random.random()  # noqa: S311 -- cosmetic
    if used_hues:
        # We pick the first candidate that is far enough from existing
        # colours, and fall back to the best we’ve found.
        best_hue = hue
        best_dist = _hue_min_distance(hue, used_hues)
        for _candidate in range(16):
            if best_dist >= hue_separation:
                break
            candidate = random.random()  # noqa: S311 -- cosmetic
            candidate_dist = _hue_min_distance(candidate, used_hues)
            if candidate_dist > best_dist:
                best_hue, best_dist = candidate, candidate_dist
        hue = best_hue

    # A luminance of 0.18 is good against both light and dark and fits our 2.5
    # colorpicker.js threshold. The full safe band is ~[0.1,0.37], so this
    # puts us in the middle and leaves some rounding slack.
    lightness = _lightness_for_luminance(hue, saturation, 0.18)
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
