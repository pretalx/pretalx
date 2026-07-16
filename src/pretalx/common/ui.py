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


# Primary-coloured text sits on two dark surfaces: --color-bg (#121416, e.g. the
# footer) and --color-grey-lightest (e.g. the skip link). The latter is lighter,
# so it decides legibility -- but it is itself brand-dependent, being
# --color-offwhite tinted with 5% of the brand colour, so we derive it below
# rather than hardcode it. Keep in sync with the dark block of _variables.css.
DARK_MODE_OFFWHITE = "#1a1d20"
DARK_MODE_SURFACE_TINT = 0.05
# The mix toward white that the dark block already applies to --color-primary-text.
DARK_MODE_TEXT_MIX = 0.1
# ... and to --color-primary-text-dark, which feeds --highlight-color-text.
DARK_MODE_TEXT_DARK_MIX = 0.4


def _parse_hex(color):
    hex_color = color.lstrip("#")
    if len(hex_color) == 3:  # The colour field permits the short #abc form
        hex_color = "".join(char * 2 for char in hex_color)
    try:
        return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return None


def _contrast_ratio(rgb, other_rgb):
    luminances = (_relative_luminance(*rgb), _relative_luminance(*other_rgb))
    return (max(luminances) + 0.05) / (min(luminances) + 0.05)


def _mix_with_white(rgb, ratio):
    """Mirror CSS ``color-mix(in srgb, <colour>, white <ratio>)``.

    The srgb colour space interpolates gamma-encoded channels, so this is a
    plain lerp of the 0-255 values rather than a linear-light blend.
    """
    return tuple(channel * (1 - ratio) + ratio for channel in rgb)


def _to_hex(rgb):
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)


def _dark_mode_surface(rgb):
    """The lightest dark surface this brand's text lands on, i.e.
    --color-grey-lightest: color-mix(in srgb, #1a1d20 95%, var(--color-primary)).
    """
    offwhite = _parse_hex(DARK_MODE_OFFWHITE)
    return tuple(
        base * (1 - DARK_MODE_SURFACE_TINT) + tint * DARK_MODE_SURFACE_TINT
        for base, tint in zip(offwhite, rgb)
    )


def dark_mode_text_override(color, floor=DARK_MODE_TEXT_MIX, threshold=4.5):
    """Return the hex that a primary ``-text`` token has to be overridden with in
    the dark colour scheme, or None if no override is needed.

    CSS cannot branch on a colour's luminance, so the dark colour scheme lifts
    every ``-text`` token toward white by a fixed amount. That is fine for the
    tokens built on a hue we picked, but the event's brand colour is arbitrary:
    a dark brand stays illegible however the stylesheet mixes it (#1a1a2e lifted
    by the stylesheet's ``floor`` of 10% reaches only 1.45:1). So we compute the
    required lift here, and event_css emits it as a dark-only override.

    None means "leave the stylesheet alone": either the brand is already legible
    at ``floor``, or it is unparseable. Emitting nothing rather than an equivalent
    hex keeps those brands rendering exactly as they do today, to the pixel --
    our hex is 8-bit, whereas the stylesheet's color-mix keeps full precision.
    """
    rgb = _parse_hex(color)
    if rgb is None:
        return None
    # Clearing the lightest surface clears the darker ones too.
    surface = _dark_mode_surface(rgb)
    # Unrounded, because this is what the browser renders if we stay out of it.
    if _contrast_ratio(_mix_with_white(rgb, floor), surface) >= threshold:
        return None
    for percent in range(round(floor * 100) + 1, 101):
        # Compare the rounded hex, since that is what the browser will paint.
        candidate = _to_hex(_mix_with_white(rgb, percent / 100))
        if _contrast_ratio(_parse_hex(candidate), surface) >= threshold:
            return candidate
    return "#ffffff"


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
