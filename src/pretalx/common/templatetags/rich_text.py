# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

# This module uses lazy factories because bleach AND markdown AND
# publicsuffixlist are slow to import and hurt pretalx startup time
# when imported at top-level. As Django imports all templatetags
# at startup time in development/check mode, that hurts in development.

import html
import re
from functools import cache, partial

from django import template
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe

from pretalx.common.views.redirect import safelink as sl

register = template.Library()


ALLOWED_TAGS = {
    "a",  # Keep in first position for link_cleaner
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "em",
    "hr",
    "i",
    "ins",
    "li",
    "ol",
    "strong",
    "ul",
    "p",
    "pre",
    "span",
    "table",
    "tbody",
    "thead",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "abbr": ["title"],
    "acronym": ["title"],
    "table": ["width"],
    "td": ["width", "align"],
    "div": ["class"],
    "p": ["class"],
    "span": ["class"],
}

ALLOWED_PROTOCOLS = {"http", "https", "mailto", "tel"}

STRIKETHROUGH_RE = "(~{2})(.+?)(~{2})"

# Regex matching list markers at the start of line, including all markers
# supported for unordered lists (*, +, -) as well as 1. for ordered lists.
# All other numbers are not supported without a preceding empty line in
# CommonMark and other common implementations due to the risk of false
# positives when people use line breaks. Capped to three preceding spaces
# to prevent matching indent-based code blocks.
LIST_INTERRUPT_RE = re.compile(r"^ {0,3}(?:[*+-]|1\.)[ ]+\S")


def link_callback(attrs, is_new, **kwargs):
    """Makes sure external links open safely."""
    safelink = kwargs.get("safelink", True)
    url = attrs.get((None, "href"), "/")
    if (
        url.startswith(("mailto:", "tel:"))
        # Exclude internal links
        or url_has_allowed_host_and_scheme(url, allowed_hosts=None)
    ):
        return attrs
    attrs[None, "target"] = "_blank"
    attrs[None, "rel"] = "noopener"
    if safelink:
        url = html.unescape(url)
        attrs[None, "href"] = sl(url)
    return attrs


safelink_callback = partial(link_callback, safelink=True)
abslink_callback = partial(link_callback, safelink=False)


@cache
def allowed_tlds():
    """The set of TLDs we autolink, taken from publicsuffixlist.

    Sorted reverse so longer TLDs win against shorter substring TLDs
    (e.g. ``.com`` matches before ``.co`` when scanning a string)."""
    from publicsuffixlist import PublicSuffixList  # noqa: PLC0415 -- slow import

    return sorted(
        {
            suffix.rsplit(".")[-1]
            for suffix in PublicSuffixList()._publicsuffix  # noqa: SLF001 -- publicsuffix2 internal
        },
        reverse=True,
    )


@cache
def link_regexes():
    """Return (url_re, email_re) compiled from ``allowed_tlds()``."""
    import bleach  # noqa: PLC0415 -- slow import

    tlds = allowed_tlds()
    return (
        bleach.linkifier.build_url_re(tlds=tlds, protocols=ALLOWED_PROTOCOLS),
        bleach.linkifier.build_email_re(tlds=tlds),
    )


def _build_linkify_filter(callback, *, skip_tags):
    import bleach  # noqa: PLC0415 -- slow import

    url_re, email_re = link_regexes()
    return partial(
        bleach.linkifier.LinkifyFilter,
        url_re=url_re,
        parse_email=True,
        email_re=email_re,
        skip_tags=skip_tags,
        callbacks=[*bleach.linkifier.DEFAULT_CALLBACKS, callback],
    )


@cache
def safelink_cleaner():
    import bleach  # noqa: PLC0415 -- slow import

    return bleach.Cleaner(
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        filters=[_build_linkify_filter(safelink_callback, skip_tags={"pre", "code"})],
    )


@cache
def abslink_cleaner():
    import bleach  # noqa: PLC0415 -- slow import

    return bleach.Cleaner(
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        filters=[_build_linkify_filter(abslink_callback, skip_tags={"pre", "code"})],
    )


@cache
def no_links_cleaner():
    """Allow formatting markup but strip ``<a>`` entirely.

    Used to render untrusted, user-authored markdown (bios, long answers)
    where we want the formatting through but won't autolink bare URLs."""
    import bleach  # noqa: PLC0415 -- slow import

    return bleach.Cleaner(
        tags=ALLOWED_TAGS - {"a"},
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


@cache
def mail_body_cleaner():
    """Cleaner used on the outer mail-body markdown pass.

    Skips autolinking inside ``<span>`` and ``<div>`` wrappers — that's how
    untrusted placeholder classes fence their output off from the outer
    pipeline. Organiser-authored bare URLs in the surrounding template are
    still autolinked."""
    import bleach  # noqa: PLC0415 -- slow import

    return bleach.Cleaner(
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        filters=[
            _build_linkify_filter(
                abslink_callback, skip_tags={"pre", "code", "span", "div"}
            )
        ],
    )


@cache
def plaintext_cleaner():
    import bleach  # noqa: PLC0415 -- slow import

    return bleach.Cleaner(tags=set(), strip=True)


@cache
def markdown_engine():
    """Return the shared ``markdown.Markdown`` instance. Inline because
    importing Markdown is slow.

    The Markdown instance is stateful, you must call .reset() before
    calling .convert()."""
    import markdown  # noqa: PLC0415 -- slow import

    class StrikeThroughExtension(markdown.Extension):
        def extendMarkdown(self, md):
            md.inlinePatterns.register(
                markdown.inlinepatterns.SimpleTagPattern(STRIKETHROUGH_RE, "del"),
                "strikethrough",
                200,
            )

    class BreaklessListPreprocessor(markdown.preprocessors.Preprocessor):
        """Insert a blank line before a list.

        Python-Markdown is committed to matching Markdown.pl rather
        de-facto standards like CommonMark, GHFM etc. Requiring an
        empty line before lists is a super common footgun, so we insert
        an empty line when we infer (see regex comment) that the user
        intended to start a list."""

        def run(self, lines):
            new_lines = []
            previous_was_list_item = False
            for line in lines:
                if LIST_INTERRUPT_RE.match(line):
                    # Only inserting before the first list item so that
                    # a tight list remains tight.
                    if not previous_was_list_item:
                        new_lines.append("")
                    previous_was_list_item = True
                elif not line.strip():
                    previous_was_list_item = False
                new_lines.append(line)
            return new_lines

    class BreaklessListExtension(markdown.Extension):
        def extendMarkdown(self, md):
            md.preprocessors.register(
                # Low priority chosen to not accidentally put lists in
                # fenced code blocks.
                BreaklessListPreprocessor(md),
                "breakless_lists",
                6,
            )

    return markdown.Markdown(
        extensions=[
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
            "markdown.extensions.md_in_html",
            StrikeThroughExtension(),
            BreaklessListExtension(),
        ]
    )


def render_markdown(text: str, cleaner=None) -> str:
    """Process markdown and cleans HTML in a text input."""
    if not text:
        return ""
    if cleaner is None:
        cleaner = safelink_cleaner()
    body_md = cleaner.clean(markdown_engine().reset().convert(str(text)))
    return mark_safe(body_md)  # noqa: S308  -- sanitised by bleach cleaner


def render_markdown_abslinks(text: str) -> str:
    """Process markdown and cleans HTML in a text input, but use absolute links instead
    of safelink redirects."""
    return render_markdown(text, cleaner=abslink_cleaner())


def render_mail_body(text: str) -> str:
    """Render a placeholder-substituted mail body to HTML.

    Identical to :func:`render_markdown_abslinks` in everything except
    the underlying cleaner: :func:`mail_body_cleaner` skips autolinking
    inside ``<span>`` and ``<div>`` wrappers, which is how the untrusted
    placeholder classes fence off their output. Organiser-authored bare
    URLs in the surrounding template text are still autolinked."""
    return render_markdown(text, cleaner=mail_body_cleaner())


def render_markdown_no_links(text: str) -> str:
    """Render markdown but strip every ``<a>`` from the output.

    Used by untrusted-content placeholders that need formatting through
    without letting authored URLs become live links."""
    return render_markdown(text, cleaner=no_links_cleaner())


def render_markdown_plaintext(text: str) -> str:
    """Render markdown to HTML, then strip all tags to produce plain text."""
    if not text:
        return ""
    result = plaintext_cleaner().clean(markdown_engine().reset().convert(str(text)))
    return result.strip()


@register.filter
def rich_text(text: str):
    return render_markdown(text)


@register.filter
def rich_text_without_links(text: str):
    """Process markdown and cleans HTML in a text input, but without links."""
    return render_markdown(text, cleaner=no_links_cleaner())


@register.filter
def rich_text_abslinks(text: str) -> str:
    return render_markdown_abslinks(text)
