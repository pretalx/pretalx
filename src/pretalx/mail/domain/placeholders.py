# SPDX-FileCopyrightText: 2021-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
"""Mail text placeholder classes.

+-----------+-----------------------------------+--------------------------------------+
|           | Plain                             | Markdown                             |
+===========+===================================+======================================+
| Trusted   | TrustedPlainMailTextPlaceholder   | TrustedMarkdownMailTextPlaceholder   |
|           |                                   |                                      |
|           | Short, organiser- or system-owned | Organiser- or system-authored        |
|           | strings (event name, slug, room,  | markdown source; autolinked.         |
|           | session type, dates, counts).     | Used for ``all_reviews`` and         |
|           |                                   | schedule-change summaries.           |
+-----------+-----------------------------------+--------------------------------------+
| Untrusted | UntrustedPlainMailTextPlaceholder | UntrustedMarkdownMailTextPlaceholder |
|           |                                   |                                      |
|           | Short user-provided strings       | Long-form user-authored markdown     |
|           | (speaker name, submission title,  | (bios, long answers). Formatting     |
|           | answer text).                     | allowed, links stripped.             |
+-----------+-----------------------------------+--------------------------------------+

If in doubt, pick Untrusted variants: over-escaping trusted content is
only cosmetic, over-trusting is dangerous.
"""

import re

from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from pretalx.common.text.formatting import (
    MODE_PLAIN,
    EmailAlternativeString,
    defuse_markdown_links,
)

# Paired angle brackets only, so content like ``Sam <3`` survives.
_HTML_TAG_LIKE_RE = re.compile(r"<[^>]*>")

_NEWLINE_RE = re.compile(r"\r\n?|\n")


def escape_for_plain_body(value) -> str:
    """Plain-variant escape for untrusted content: strip HTML-tag-like
    sequences and backslash-escape markdown link metacharacters."""
    return defuse_markdown_links(
        _HTML_TAG_LIKE_RE.sub("", str(value or "")), mode=MODE_PLAIN
    )


def escape_for_html_body(value) -> str:
    """HTML-variant escape for untrusted content: HTML-escape tag
    characters, entity-encode markdown link brackets, and collapse
    newlines to ``<br>`` to keep the surrounding ``<span>`` fence intact."""
    escaped = conditional_escape(str(value or ""))
    escaped = defuse_markdown_links(escaped)
    return _NEWLINE_RE.sub("<br>", escaped)


def untrusted_plain_value(value) -> EmailAlternativeString:
    """Build an :class:`EmailAlternativeString` for a raw untrusted
    string. Use to pass a per-call untrusted value through
    ``safe_extra_context`` when no registered placeholder fits."""
    return EmailAlternativeString(
        plain=escape_for_plain_body(value),
        html=f"<span>{escape_for_html_body(value)}</span>",
    )


class BaseMailTextPlaceholder:
    """Base class for all email text placeholders."""

    @property
    def required_context(self):
        """Keys this placeholder needs in the render context."""
        return ["event"]

    @property
    def identifier(self):
        """Unique key the placeholder is referenced by in templates."""
        raise NotImplementedError

    @property
    def is_visible(self):
        """Set ``False`` to hide from the placeholder picker (e.g. aliases)."""
        return True

    def render(self, context):
        """Return the rendered value given a context dict."""
        raise NotImplementedError

    def render_sample(self, event):
        """Return a preview value that depends only on ``event``."""
        raise NotImplementedError

    def render_sample_for_preview(self, event):
        """Shape the sample like :meth:`render`'s output so the preview
        pipeline matches delivery."""
        return self.render_sample(event)

    @property
    def explanation(self):
        return ""


class TrustedPlainMailTextPlaceholder(BaseMailTextPlaceholder):
    """Trusted, plain-string placeholder. Value is inserted verbatim
    in plain mode and HTML-escaped (but not markdown-escaped) in HTML
    mode."""

    def __init__(
        self, identifier, args, func, sample, explanation=None, is_visible=True
    ):
        self._identifier = identifier
        self._args = args
        self._func = func
        self._sample = sample
        self._explanation = explanation
        self._is_visible = is_visible

    def __repr__(self):
        return f"TrustedPlainMailTextPlaceholder({self._identifier})"

    @property
    def identifier(self):
        return self._identifier

    @property
    def required_context(self):
        return self._args

    @property
    def explanation(self):
        return self._explanation or ""

    @property
    def is_visible(self):
        return self._is_visible

    def render(self, context):
        return self._func(**{key: context[key] for key in self._args})

    def render_sample(self, event):
        if callable(self._sample):
            return self._sample(event)
        return self._sample


# Legacy alias
SimpleFunctionalMailTextPlaceholder = TrustedPlainMailTextPlaceholder


class BaseRichMailTextPlaceholder(BaseMailTextPlaceholder):
    """Base for placeholders that emit different plain-text and HTML
    variants. Subclasses override :meth:`_render_plain_value` and
    :meth:`_render_html_value`; :meth:`render` wraps the pair in an
    :class:`EmailAlternativeString` for the formatter to dispatch on."""

    def __init__(self, identifier, args, sample, explanation=None, is_visible=True):
        self._identifier = identifier
        self._args = args
        self._sample = sample
        self._explanation = explanation
        self._is_visible = is_visible

    @property
    def identifier(self):
        return self._identifier

    @property
    def required_context(self):
        return self._args

    @property
    def explanation(self):
        return self._explanation or ""

    @property
    def is_visible(self):
        return self._is_visible

    def _render_plain_value(self, value):
        raise NotImplementedError

    def _render_html_value(self, value):
        raise NotImplementedError

    def render_plain(self, **kwargs):
        return self._render_plain_value(self._func(**kwargs))

    def render_html(self, **kwargs):
        return self._render_html_value(self._func(**kwargs))

    def render(self, context):
        kwargs = {key: context[key] for key in self._args}
        return EmailAlternativeString(
            self.render_plain(**kwargs), self.render_html(**kwargs)
        )

    def render_sample(self, event):
        if callable(self._sample):
            return self._sample(event)
        return self._sample

    def render_sample_for_preview(self, event):
        # Coerce to ``str`` so lazy i18n samples match the plain-string
        # shape ``self._func`` returns in production and satisfy
        # ``EmailAlternativeString``'s type guard.
        sample = str(self.render_sample(event) or "")
        return EmailAlternativeString(
            self._render_plain_value(sample), self._render_html_value(sample)
        )


class LinkMailTextPlaceholder(BaseRichMailTextPlaceholder):
    """Trusted placeholder for internally-built URLs. Emits the raw URL
    in plain mode and ``mark_safe``-wraps it in HTML mode so query-
    string ``&`` survives into the linkifier. Use only for URLs pretalx
    builds itself, never for URLs read from user input."""

    def __init__(
        self, identifier, args, func, sample, explanation=None, is_visible=True
    ):
        super().__init__(
            identifier, args, sample, explanation=explanation, is_visible=is_visible
        )
        self._func = func

    def __repr__(self):
        return f"LinkMailTextPlaceholder({self._identifier})"

    def _render_plain_value(self, value):
        return value

    def _render_html_value(self, value):
        return mark_safe(str(value))  # noqa: S308  -- internally-built URL


class TrustedMarkdownMailTextPlaceholder(BaseRichMailTextPlaceholder):
    """Placeholder whose output is trusted markdown source. Plain mode
    returns the source verbatim; HTML mode renders through the standard
    markdown/bleach pipeline with ``<a>`` and bare-URL autolinking
    allowed. Use only for pretalx-generated or organiser-authored
    content."""

    def __init__(
        self, identifier, args, func, sample, explanation=None, is_visible=True
    ):
        super().__init__(
            identifier, args, sample, explanation=explanation, is_visible=is_visible
        )
        self._func = func

    def __repr__(self):
        return f"TrustedMarkdownMailTextPlaceholder({self._identifier})"

    def _render_plain_value(self, value):
        return value

    def _render_html_value(self, value):
        from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- avoid circular import
            render_markdown_abslinks,
        )

        return mark_safe(  # noqa: S308  -- render_markdown_abslinks sanitises via bleach
            render_markdown_abslinks(str(value))
        )


# Legacy alias
MarkdownMailTextPlaceholder = TrustedMarkdownMailTextPlaceholder


class UntrustedPlainMailTextPlaceholder(BaseRichMailTextPlaceholder):
    """Placeholder for short user-authored strings. Plain mode strips
    HTML-tag-like sequences and backslash-escapes markdown link syntax;
    HTML mode HTML-escapes, entity-encodes brackets, collapses newlines
    to ``<br>``, and wraps the value in a ``<span>`` so the outer mail-
    body pipeline treats it as inert text. Bare URLs survive as
    autolinks only where label and href match."""

    def __init__(
        self, identifier, args, func, sample, explanation=None, is_visible=True
    ):
        super().__init__(
            identifier, args, sample, explanation=explanation, is_visible=is_visible
        )
        self._func = func

    def __repr__(self):
        return f"UntrustedPlainMailTextPlaceholder({self._identifier})"

    def _render_plain_value(self, value):
        return escape_for_plain_body(value)

    def _render_html_value(self, value):
        # Two defenses must coexist: the ``<span>`` fences the value
        # from the outer ``MAIL_BODY_CLEANER``'s autolinker, and the
        # newline collapse in ``escape_for_html_body`` stops a blank
        # line from breaking out via markdown's paragraph splitter.
        # Dropping either reopens the hole.
        return f"<span>{escape_for_html_body(value)}</span>"


class UntrustedMarkdownMailTextPlaceholder(BaseRichMailTextPlaceholder):
    """Placeholder for long-form user-authored markdown (bios, long
    answers). Plain mode strips to plain text; HTML mode renders and
    cleans via ``NO_LINKS_CLEANER`` (formatting allowed, ``<a>``
    stripped) and wraps in a ``<div>`` to block outer-pipeline
    autolinking of bare URLs the user wrote."""

    def __init__(
        self, identifier, args, func, sample, explanation=None, is_visible=True
    ):
        super().__init__(
            identifier, args, sample, explanation=explanation, is_visible=is_visible
        )
        self._func = func

    def __repr__(self):
        return f"UntrustedMarkdownMailTextPlaceholder({self._identifier})"

    def _render_plain_value(self, value):
        from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- slow import
            PLAINTEXT_CLEANER,
            md,
        )

        value = str(value or "")
        if not value:
            return ""
        return PLAINTEXT_CLEANER.clean(md.reset().convert(value)).strip()

    def _render_html_value(self, value):
        from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415 -- slow import
            NO_LINKS_CLEANER,
            md,
        )

        value = str(value or "")
        if not value:
            return "<div></div>"
        rendered = NO_LINKS_CLEANER.clean(md.reset().convert(value))
        # ``render_mail_body`` runs a second markdown pass on the outer
        # template; entity-encode ``[``/``]`` so a ``[text](url)``
        # payload can't reassemble into a link after our ``<a>`` strip.
        rendered = defuse_markdown_links(rendered)
        return f"<div>{rendered}</div>"
