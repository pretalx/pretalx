# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import re
from decimal import Decimal
from string import Formatter

from django.core.exceptions import SuspiciousOperation
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.safestring import SafeString
from i18nfield.strings import LazyI18nString

logger = logging.getLogger(__name__)


MODE_PLAIN = 1
MODE_HTML = 2


# The three characters markdown needs to recognise a link: ``[`` and
# ``]`` delimit inline/reference link and image syntax, and ``\`` is
# included so an existing backslash in the input is itself escaped and
# cannot pair up with the ``[`` we emit to re-enable link parsing.
_MARKDOWN_LINK_CHARS_RE = re.compile(r"([\\\[\]])")


def defuse_markdown_links(value: str, *, mode: int = MODE_HTML) -> str:
    """Neutralise markdown inline/reference/image link syntax so
    ``[label](url)`` cannot render as a live link downstream. Only
    brackets are touched — emphasis and parens are harmless on their
    own, and escaping them would pepper names like ``Jane (she/her)``.

    ``MODE_HTML`` (default) entity-encodes ``[`` and ``]``; entities
    survive any number of markdown passes. Use for HTML bodies and for
    markdown source that may be re-rendered.

    ``MODE_PLAIN`` backslash-escapes ``\\``, ``[``, ``]``; backslashes
    are consumed on the first markdown pass. Use for plain-text bodies
    (entities would leak as literal ``&#91;``) or markdown source that
    sees only a single pass."""
    if mode == MODE_PLAIN:
        return _MARKDOWN_LINK_CHARS_RE.sub(r"\\\1", value)
    return value.replace("[", "&#91;").replace("]", "&#93;")


class EmailAlternativeString:
    """A string-like value with separate plain-text and HTML representations."""

    def __init__(self, plain, html):
        if not isinstance(plain, str) or not isinstance(html, str):
            raise TypeError(
                "EmailAlternativeString requires str values for both "
                f"'plain' and 'html'; got plain={type(plain).__name__!r}, "
                f"html={type(html).__name__!r}."
            )
        self.plain = plain
        self.html = html

    def __repr__(self):
        return f"EmailAlternativeString('{self.plain}', '{self.html}')"


class FormattedString(str):
    """A :class:`str` subclass marking a value as "already formatted" so
    :func:`format_map` can refuse to format it again.
    Double-formatting a string can easily negate injection protection,
    so any rendering of user-controlled data must only be rendered once."""

    __slots__ = ()

    def __str__(self):
        # Returning ``self`` so that even after string-conversion,
        # we still know that this string has already been formatted.
        return self


class SafeFormatter(Formatter):
    """Customised version of :meth:`str.format_map` that behaves
    like ``format_map``, blocks attribute access and format specifiers
    as defense against Python format-string abuse, and dispatches
    :class:`EmailAlternativeString` values on a rendering mode so
    the same context dict can be used for both plain-text and HTML
    output."""

    def __init__(self, context, raise_on_missing=True, mode=MODE_PLAIN):
        self.context = context
        self.raise_on_missing = raise_on_missing
        self.mode = mode

    def get_field(self, field_name, args, kwargs):
        return self.get_value(field_name, args, kwargs), field_name

    def get_value(self, key, args, kwargs):
        if not self.raise_on_missing and key not in self.context:
            return "{" + str(key) + "}"
        return self.context[key]

    def _prepare_value(self, value):
        if isinstance(value, EmailAlternativeString):
            return value.plain if self.mode == MODE_PLAIN else value.html

        # These types can be safely coerced to a string. We reject everything
        # else so that a bad placeholder or ``safe_extra_context`` data cannot
        # break the trust boundary.
        # Promise is for lazy gettext strings.
        allowed_types = (str, int, float, Decimal, Promise, LazyI18nString)
        if not isinstance(value, allowed_types):
            raise TypeError(
                f"Cannot safely format data of type {type(value).__name__!r}"
            )
        is_safe = isinstance(value, SafeString)
        value = str(value)
        if self.mode == MODE_HTML and not is_safe:
            # Defensive backstop for ``TrustedPlain…`` placeholders and
            # coerced numerics: HTML-escape and defuse markdown link
            # syntax so a misclassified placeholder can't leak tag or
            # link content. ``SafeString`` (internal URLs, pre-escaped
            # counters, ``safe_extra_context``) bypasses both steps so
            # ``&`` in URLs stays unescaped and linkifiable.
            #
            # ``mode=MODE_PLAIN`` is deliberate despite the HTML branch:
            # our output is markdown source that
            # :func:`~pretalx.common.templatetags.rich_text.render_mail_body`
            # will parse exactly once (the only MODE_HTML call sites
            # all feed straight into it), so backslash escapes survive
            # to block the link regex and are then consumed by that
            # single pass. Entity encoding is reserved for content that
            # meets a *second* markdown pass — i.e. values already
            # rendered to HTML upstream (see
            # :func:`~pretalx.mail.placeholders.escape_for_html_body`
            # and :meth:`UntrustedMarkdownMailTextPlaceholder._render_html_value`).
            value = defuse_markdown_links(conditional_escape(value), mode=MODE_PLAIN)
        return value

    def format_field(self, value, format_spec):
        # Ignore format_spec to block things like ``{x:!r}``.
        return super().format_field(self._prepare_value(value), "")

    def convert_field(self, value, conversion):
        # Ignore any conversions (``{x!r}``, ``{x!s}``, ``{x!a}``) so
        # the output of ``{name}`` and ``{name!r}`` is identical.
        return value


def format_map(template, context, raise_on_missing=True, mode=MODE_PLAIN):
    if isinstance(template, FormattedString):
        raise SuspiciousOperation(
            "A FormattedString cannot be formatted a second time."
        )
    if not isinstance(template, str):
        template = str(template)
    return FormattedString(
        SafeFormatter(context, raise_on_missing, mode=mode).format(template)
    )
