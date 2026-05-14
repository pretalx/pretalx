# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.common.language import language
from pretalx.common.text.formatting import MODE_HTML, format_map
from pretalx.mail.domain.placeholders import get_invalid_placeholders


def validate_text_placeholders(text, valid_placeholders):
    """Reject template text containing unknown or malformed
    ``{placeholder}`` references. ``valid_placeholders`` is an iterable of
    identifier strings (or a mapping keyed by them)."""
    try:
        invalid = get_invalid_placeholders(text, valid_placeholders)
    except ValueError:
        raise ValidationError(
            _(
                "Invalid email template! "
                "Please check that you don’t have stray { or } somewhere, "
                "and that there are no spaces inside the {} blocks."
            )
        ) from None
    if invalid:
        rendered = ", ".join("{" + name + "}" for name in invalid)
        raise ValidationError(str(_("Unknown placeholder!")) + " " + rendered)


def validate_text_no_empty_links(text, valid_placeholders, event):
    """Reject template text whose rendered preview contains an empty-href
    ``<a>`` — typically a markdown ``[label]()`` an author left behind.
    Renders the same preview pipeline as delivery to catch the markup
    organisers actually receive."""
    if not text:
        return

    from bs4 import BeautifulSoup  # noqa: PLC0415 -- slow import

    from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- predicate
        render_mail_body,
    )

    preview_context = {
        key: value.render_sample_for_preview(event)
        for key, value in valid_placeholders.items()
    }
    for locale in event.locales:
        with language(locale):
            message = text.localize(locale) if hasattr(text, "localize") else text
            preview_text = render_mail_body(
                format_map(message, preview_context, mode=MODE_HTML)
            )
            doc = BeautifulSoup(preview_text, "lxml")
            for link in doc.find_all("a"):
                if link.attrs.get("href") in (None, "", "http://", "https://"):
                    raise ValidationError(
                        _(
                            "You have an empty link in your email, labeled “{text}”!"
                        ).format(text=link.text)
                    )
