# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django.templatetags.static import static

from pretalx.common.signals import register_fonts


def get_fonts(event=None):
    """Collect all fonts registered by plugins for the given event.

    Returns a dict mapping font family names to their font data dicts.
    """
    if not event or not event.pk:
        return {}

    received = {}
    for _receiver, value in register_fonts.send_robust(event):
        if isinstance(value, dict):
            received.update(value)
    return received


def get_font_definitions(fonts, selected_fonts):
    """Generate @font-face CSS rules for the given font families.

    Args:
        fonts: dict from get_fonts() — all available fonts
        selected_fonts: iterable of font family names to generate rules for
    Returns:
        str of @font-face CSS rules
    """
    rules = []
    for font_name in selected_fonts:
        if font_name not in fonts:
            continue
        font = fonts[font_name]
        for variant, formats in font.items():
            if not isinstance(formats, dict):
                continue
            srcs = [
                f"url('{static(formats[fmt])}') format('{fmt}')"
                for fmt in ("woff2", "woff", "truetype")
                if fmt in formats
            ]
            if not srcs:
                continue
            rules.append("@font-face {")
            rules.append(f'  font-family: "{font_name}";')
            if variant in ("italic", "bolditalic"):
                rules.append("  font-style: italic;")
            else:
                rules.append("  font-style: normal;")
            if variant in ("bold", "bolditalic"):
                rules.append("  font-weight: bold;")
            else:
                rules.append("  font-weight: normal;")
            rules.append(f"  src: {', '.join(srcs)};")
            rules.append("  font-display: swap;")
            rules.append("}")
    return "\n".join(rules)


def get_font_css(event):
    """Generate CSS for event-selected custom fonts.

    Returns @font-face rules and CSS variable overrides, or empty string
    if no custom fonts are selected.
    """
    heading_font = event.display_settings.get("heading_font", "")
    text_font = event.display_settings.get("text_font", "")

    if not heading_font and not text_font:
        return ""

    fonts = get_fonts(event)
    if not fonts:
        return ""

    selected = set()
    if heading_font and heading_font in fonts:
        selected.add(heading_font)
    if text_font and text_font in fonts:
        selected.add(text_font)

    if not selected:
        return ""

    parts = []
    font_face_css = get_font_definitions(fonts, selected)
    if font_face_css:
        parts.append(font_face_css)

    fallback = "var(--font-fallback)"
    variables = []
    if heading_font and heading_font in fonts:
        variables.append(f'  --font-family-title: "{heading_font}", {fallback};')
    if text_font and text_font in fonts:
        variables.append(f'  --font-family: "{text_font}", {fallback};')
    parts.append(":root {\n" + "\n".join(variables) + "\n}")

    return "\n".join(parts)
