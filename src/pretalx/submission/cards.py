# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import tempfile
import unicodedata

import reportlab.rl_config
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.utils.html import conditional_escape
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, PageTemplate, Paragraph

_fonts_registered = False


def _register_default_fonts():
    global _fonts_registered  # noqa: PLW0603
    if _fonts_registered:
        return
    reportlab.rl_config.TTFSearchPath.append(finders.find("fonts"))
    pdfmetrics.registerFont(TTFont("Muli", "mulish-v12-latin-ext-regular.ttf"))
    pdfmetrics.registerFont(TTFont("Muli-Italic", "mulish-v12-latin-ext-italic.ttf"))
    pdfmetrics.registerFont(
        TTFont("Titillium-Bold", "titillium-web-v17-latin-ext-600.ttf")
    )
    _fonts_registered = True


def _register_plugin_font(font_name, font_data):
    """Register a plugin-provided font with reportlab for PDF rendering.

    Returns the set of variant names that were successfully registered.
    """
    registered_names = pdfmetrics.getRegisteredFontNames()
    registered_variants = set()
    for variant in ("regular", "bold", "italic", "bolditalic"):
        if variant not in font_data or not isinstance(font_data[variant], dict):
            continue
        ttf_path = font_data[variant].get("truetype")
        if not ttf_path:
            continue
        resolved = finders.find(ttf_path)
        if not resolved:
            continue
        suffix_map = {
            "regular": "",
            "bold": "-Bold",
            "italic": "-Italic",
            "bolditalic": "-BoldItalic",
        }
        reg_name = font_name + suffix_map[variant]
        if reg_name not in registered_names:
            pdfmetrics.registerFont(TTFont(reg_name, resolved))
        registered_variants.add(variant)
    return registered_variants


def _text(text, max_length=None):
    if not text:
        return ""

    # Reportlab does not support unicode combination characters
    text = unicodedata.normalize("NFC", conditional_escape(text))

    if max_length and len(text) > max_length:
        text = text[: max_length - 1] + "…"

    # add an almost-invisible space &hairsp; after hyphens as word-wrap in ReportLab only works on space chars
    return text.replace("-", "-&hairsp;")


class SubmissionCard(Flowable):
    def __init__(self, submission, styles, width, heading_font_name):
        super().__init__()
        self.submission = submission
        self.styles = styles
        self.width = width
        self.height = min(2.5 * max(submission.get_duration(), 30) * mm, A4[1])
        self.text_location = 0
        self.heading_font_name = heading_font_name

    def coord(self, x, y, unit=1):
        """http://stackoverflow.com/questions/4726011/wrap-text-in-a-table-
        reportlab Helper class to help position flowables in Canvas objects."""
        return x * unit, self.height - y * unit

    def render_paragraph(self, paragraph, gap=2):
        _, height = paragraph.wrapOn(self.canv, self.width - 30 * mm, 50 * mm)
        self.text_location += height + gap * mm
        paragraph.drawOn(self.canv, *self.coord(20 * mm, self.text_location))

    def draw(self):
        self.text_location = 0
        self.canv.rect(0, 0, self.width, self.height)

        self.canv.rotate(90)
        self.canv.setFont(self.heading_font_name, 16)
        self.canv.drawString(
            25 * mm, -12 * mm, _text(self.submission.submission_type.name)
        )
        self.canv.rotate(-90)

        qr_code = qr.QrCodeWidget(self.submission.orga_urls.quick_schedule.full())
        bounds = qr_code.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        drawing = Drawing(45, 45, transform=[45 / width, 0, 0, 45 / height, 0, 0])
        drawing.add(qr_code)
        renderPDF.draw(drawing, self.canv, 15, 10)

        self.render_paragraph(
            Paragraph(_text(self.submission.title), style=self.styles["Title"]), gap=10
        )
        self.render_paragraph(
            Paragraph(
                _text(
                    ", ".join(
                        s.get_display_name() for s in self.submission.sorted_speakers
                    )
                ),
                style=self.styles["Speaker"],
            )
        )
        self.render_paragraph(
            Paragraph(
                _("{} minutes, #{}, {}, {}").format(
                    self.submission.get_duration(),
                    self.submission.code,
                    self.submission.content_locale,
                    self.submission.state,
                ),
                style=self.styles["Meta"],
            )
        )

        if self.submission.abstract:
            self.render_paragraph(
                Paragraph(
                    _text(self.submission.abstract, 140), style=self.styles["Meta"]
                )
            )

        if self.submission.notes:
            self.render_paragraph(
                Paragraph(_text(self.submission.notes, 140), style=self.styles["Meta"])
            )


def _resolve_fonts(event=None):
    """Determine the reportlab font names to use for this event.

    Returns (heading_font_name, text_font_name, text_italic_font_name)
    for use with reportlab ParagraphStyle fontName. Falls back to
    built-in defaults when no event is given or no custom fonts are set.
    """
    heading_font_name = "Titillium-Bold"
    text_font_name = "Muli"
    text_italic_font_name = "Muli-Italic"

    if not event:
        return heading_font_name, text_font_name, text_italic_font_name

    from pretalx.common.fonts import get_fonts  # noqa: PLC0415

    fonts = get_fonts(event)
    heading_font_setting = event.display_settings.get("heading_font", "")
    text_font_setting = event.display_settings.get("text_font", "")

    if heading_font_setting and heading_font_setting in fonts:
        registered = _register_plugin_font(
            heading_font_setting, fonts[heading_font_setting]
        )
        if "regular" in registered:
            heading_font_name = heading_font_setting
            if "bold" in registered:
                heading_font_name = heading_font_setting + "-Bold"

    if text_font_setting and text_font_setting in fonts:
        registered = _register_plugin_font(text_font_setting, fonts[text_font_setting])
        if "regular" in registered:
            text_font_name = text_font_setting
            if "italic" in registered:
                text_italic_font_name = text_font_setting + "-Italic"
            else:
                text_italic_font_name = text_font_setting

    return heading_font_name, text_font_name, text_italic_font_name


def get_style(heading_font, text_font, text_italic_font):
    stylesheet = StyleSheet1()
    stylesheet.add(
        ParagraphStyle(name="Normal", fontName=text_font, fontSize=12, leading=14)
    )
    stylesheet.add(
        ParagraphStyle(name="Title", fontName=heading_font, fontSize=14, leading=16)
    )
    stylesheet.add(
        ParagraphStyle(
            name="Speaker", fontName=text_italic_font, fontSize=12, leading=14
        )
    )
    stylesheet.add(
        ParagraphStyle(name="Meta", fontName=text_font, fontSize=10, leading=12)
    )
    return stylesheet


def get_story(doc, queryset, event):
    heading_font, text_font, text_italic_font = _resolve_fonts(event)
    styles = get_style(heading_font, text_font, text_italic_font)
    return [SubmissionCard(s, styles, doc.width / 2, heading_font) for s in queryset]


def build_cards(queryset, event):
    _register_default_fonts()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        doc = BaseDocTemplate(
            f.name,
            pagesize=A4,
            leftMargin=0,
            rightMargin=0,
            topMargin=0,
            bottomMargin=0,
        )
        doc.addPageTemplates(
            [
                PageTemplate(
                    id="All",
                    frames=[
                        Frame(
                            0,
                            0,
                            doc.width / 2,
                            doc.height,
                            leftPadding=0,
                            rightPadding=0,
                            topPadding=0,
                            bottomPadding=0,
                            id="left",
                        ),
                        Frame(
                            doc.width / 2,
                            0,
                            doc.width / 2,
                            doc.height,
                            leftPadding=0,
                            rightPadding=0,
                            topPadding=0,
                            bottomPadding=0,
                            id="right",
                        ),
                    ],
                    pagesize=A4,
                )
            ]
        )
        doc.build(get_story(doc, queryset, event))
        f.seek(0)
        timestamp = now().strftime("%Y-%m-%d-%H%M")
        r = HttpResponse(
            content_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{event.slug}_submission_cards_{timestamp}.pdf"'
            },
        )
        r.write(f.read())
        return r
