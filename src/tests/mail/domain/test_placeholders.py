# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re

import pytest
from django.utils.safestring import SafeString

from pretalx.common.templatetags.rich_text import (
    render_mail_body,
    render_markdown_abslinks,
)
from pretalx.common.text.formatting import (
    MODE_HTML,
    MODE_PLAIN,
    EmailAlternativeString,
    format_map,
)
from pretalx.mail.placeholders import (
    BaseMailTextPlaceholder,
    LinkMailTextPlaceholder,
    MarkdownMailTextPlaceholder,
    SimpleFunctionalMailTextPlaceholder,
    TrustedMarkdownMailTextPlaceholder,
    TrustedPlainMailTextPlaceholder,
    UntrustedMarkdownMailTextPlaceholder,
    UntrustedPlainMailTextPlaceholder,
)

pytestmark = pytest.mark.unit


def _full_html_pipeline(template, context):
    # Mirror QueuedMail.make_html's text_html path.
    html = format_map(template, context, mode=MODE_HTML)
    return render_mail_body(html)


def _edited_draft_pipeline(template, context):
    # Mirror QueuedMail.make_html's fallback when text_html is None.
    plain = format_map(template, context, mode=MODE_PLAIN)
    return render_markdown_abslinks(plain)


_PHISH_LINK_RE = re.compile(r'<a[^>]*href="https://phish\.com[^"]*"[^>]*>([^<]*)</a>')


def _assert_no_misleading_phish_link(rendered, *, allow_bare_url_autolink=False):
    # A bare URL autolink (visible label == href) can't mislead, so it's
    # tolerated on the edited-draft fallback path.
    for match in _PHISH_LINK_RE.finditer(rendered):
        inner = match.group(1).strip()
        if allow_bare_url_autolink and inner == "https://phish.com":
            continue
        raise AssertionError(  # pragma: no cover
            f"Phish link with non-matching inner text: {match.group(0)!r}\n"
            f"Full rendered: {rendered!r}"
        )


_ATTACK_PAYLOADS = {
    "html_cve": (
        "user,<br>We have detected suspicious activity. "
        '<a href="https://phish.com">Click here to secure your account.</a a=">'
    ),
    "md_link": "[Click here](https://phish.com)",
    "md_image": "![image](https://phish.com)",
    "md_reference_link": "Click [here][1]\n\n[1]: https://phish.com",
    "bare_url": "Visit https://phish.com now",
    "script_tag": "<script>alert('xss')</script>",
    "html_entity_in_url": '<a href="https://ph&#x69;sh.test">click</a>',
    # Blank lines break the <span> wrapper apart and leak content
    # outside the autolinker skip_tags fence unless render_html
    # collapses newlines.
    "blank_line_bare_url": "innocent\n\nhttps://phish.com\n\nhi",
    "blank_line_heading_consume": (
        "hi\n\n# Click here to reset your password https://phish.com"
    ),
    # conditional_escape must turn <> into entities before markdown
    # sees the value, or <url> becomes a live autolink.
    "angle_bracket_autolink": "<https://phish.com>",
}


@pytest.mark.parametrize(
    ("attr", "expected"),
    (("required_context", ["event"]), ("is_visible", True), ("explanation", "")),
)
def test_base_placeholder_default_values(attr, expected):
    placeholder = BaseMailTextPlaceholder()
    assert getattr(placeholder, attr) == expected


def test_trusted_plain_renders_string_verbatim():
    p = TrustedPlainMailTextPlaceholder(
        "event_name", ["event"], lambda event: event, "sample"
    )
    result = p.render({"event": "PyCon"})
    assert result == "PyCon"
    assert not isinstance(result, EmailAlternativeString)


def test_trusted_plain_extracts_required_keys_only():
    p = TrustedPlainMailTextPlaceholder(
        "greeting",
        ["name", "event"],
        lambda name, event: f"Hello {name} at {event}",
        "sample",
    )
    assert (
        p.render({"name": "Alice", "event": "PyCon", "extra": "ignored"})
        == "Hello Alice at PyCon"
    )


@pytest.mark.parametrize(
    ("sample", "event_arg", "expected"),
    (
        ("Example Conference", None, "Example Conference"),
        (lambda event: f"Sample: {event}", "PyCon", "Sample: PyCon"),
    ),
)
def test_trusted_plain_render_sample(sample, event_arg, expected):
    p = TrustedPlainMailTextPlaceholder(
        "event_name", ["event"], lambda event: event, sample
    )
    assert p.render_sample(event_arg) == expected


def test_trusted_plain_repr():
    p = TrustedPlainMailTextPlaceholder(
        "event_name", ["event"], lambda event: event, "sample"
    )
    assert repr(p) == "TrustedPlainMailTextPlaceholder(event_name)"


def test_trusted_plain_html_mode_is_escaped_by_formatter():
    # Even trusted content is HTML-escaped in HTML mode by the
    # formatter (e.g. an event name with ``&`` or ``<``).
    context = {"event_name": "Rust & Go"}
    assert (
        format_map("Welcome to {event_name}", context, mode=MODE_PLAIN)
        == "Welcome to Rust & Go"
    )
    assert (
        format_map("Welcome to {event_name}", context, mode=MODE_HTML)
        == "Welcome to Rust &amp; Go"
    )


def test_simple_functional_is_alias_for_trusted_plain():
    # Backwards-compat alias for external plugins.
    assert SimpleFunctionalMailTextPlaceholder is TrustedPlainMailTextPlaceholder


def test_markdown_placeholder_is_alias_for_trusted_markdown():
    assert MarkdownMailTextPlaceholder is TrustedMarkdownMailTextPlaceholder


def test_link_placeholder_render_returns_dual_payload():
    p = LinkMailTextPlaceholder(
        "some_url",
        ["event"],
        lambda event: f"https://foo.test/{event}",
        "https://sample",
    )
    result = p.render({"event": "demo"})
    assert isinstance(result, EmailAlternativeString)
    assert result.plain == "https://foo.test/demo"
    assert result.html == "https://foo.test/demo"


def test_link_placeholder_html_is_safestring_to_preserve_ampersand():
    # SafeString bypasses conditional_escape so the downstream linkifier
    # sees raw ``&`` in query strings, not ``&amp;``.
    p = LinkMailTextPlaceholder(
        "some_url", ["event"], lambda event: "https://x?a=1&b=2", "sample"
    )
    result = p.render({"event": object()})
    assert isinstance(result.html, SafeString)
    assert result.html == "https://x?a=1&b=2"


def test_link_placeholder_required_context_and_visibility():
    p = LinkMailTextPlaceholder(
        "u", ["event", "user"], lambda event, user: "x", "s", is_visible=False
    )
    assert p.required_context == ["event", "user"]
    assert p.is_visible is False


def test_link_placeholder_repr():
    p = LinkMailTextPlaceholder("u", ["event"], lambda event: "x", "s")
    assert repr(p) == "LinkMailTextPlaceholder(u)"


def test_trusted_markdown_plain_is_markdown_source():
    p = TrustedMarkdownMailTextPlaceholder(
        "bullets", ["event"], lambda event: "- first\n- second", "sample"
    )
    result = p.render({"event": object()})
    assert isinstance(result, EmailAlternativeString)
    assert result.plain == "- first\n- second"


def test_trusted_markdown_html_compiles_markdown_with_links():
    # Trusted markdown is explicitly allowed to produce live links.
    p = TrustedMarkdownMailTextPlaceholder(
        "notes",
        ["event"],
        lambda event: "Visit [pretalx](https://pretalx.com) for more",
        "sample",
    )
    result = p.render({"event": object()})
    assert isinstance(result.html, SafeString)
    assert '<a href="https://pretalx.com"' in result.html


@pytest.mark.parametrize(
    ("value", "expected_plain", "expected_html"),
    (
        ("Jane Doe", "Jane Doe", "<span>Jane Doe</span>"),
        ("J.R.R. Tolkien", "J.R.R. Tolkien", "<span>J.R.R. Tolkien</span>"),
        ("Jean-Luc Picard", "Jean-Luc Picard", "<span>Jean-Luc Picard</span>"),
        ("Jane Doe (she/her)", "Jane Doe (she/her)", "<span>Jane Doe (she/her)</span>"),
        ("María-José", "María-José", "<span>María-José</span>"),
    ),
)
def test_untrusted_plain_passes_benign_content_through(
    value, expected_plain, expected_html
):
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": value})
    assert result.plain == expected_plain
    assert result.html == expected_html


def test_untrusted_plain_handles_none_as_empty_string():
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": None})
    assert result.plain == ""
    assert result.html == "<span></span>"


def test_untrusted_plain_plain_variant_strips_html_tags():
    # Stripping in the plain variant defuses the edited-draft fallback:
    # the markdown pipeline cannot re-HTML-ify what is no longer there.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": _ATTACK_PAYLOADS["html_cve"]})
    assert "<br>" not in result.plain
    assert '<a href="https://phish.com"' not in result.plain
    assert "We have detected suspicious activity" in result.plain


def test_untrusted_plain_html_variant_escapes_html_and_wraps_in_span():
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": _ATTACK_PAYLOADS["html_cve"]})
    assert result.html.startswith("<span>")
    assert result.html.endswith("</span>")
    assert "<br>" not in result.html
    assert '<a href="https://phish.com"' not in result.html
    assert "&lt;br&gt;" in result.html
    assert "&lt;a href=" in result.html


def test_untrusted_plain_plain_variant_escapes_markdown_link_chars():
    # Backslash-escaping ``[`` alone defangs inline, reference, and
    # image syntax in one pass.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": _ATTACK_PAYLOADS["md_link"]})
    assert r"\[" in result.plain
    assert r"\]" in result.plain


def test_untrusted_plain_html_variant_encodes_markdown_link_chars_as_entities():
    # HTML mode uses &#91;/&#93; entities rather than backslashes:
    # entities survive the second markdown pass in render_mail_body,
    # while backslashes are consumed on the first pass and leave a bare
    # ``[`` for the second one to parse as a link.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": _ATTACK_PAYLOADS["md_link"]})
    assert "&#91;" in result.html
    assert "&#93;" in result.html
    assert "[" not in result.html.replace("&#91;", "")
    assert "]" not in result.html.replace("&#93;", "")


def test_untrusted_plain_html_variant_collapses_newlines_to_br():
    # Otherwise markdown's paragraph splitter breaks the <span> fence
    # apart and leaks trailing content to the autolinker.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": "innocent\n\nhttps://phish.com\n\nhi"})
    assert "\n\n" not in result.html
    assert "<br>" in result.html
    assert result.html.count("<span>") == 1
    assert result.html.count("</span>") == 1


def test_untrusted_plain_preserves_parentheses_in_legit_content():
    # Only ``[`` and ``]`` are escaped, so pronouns etc. stay clean.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    result = p.render({"user": "Jane Doe (she/her)"})
    assert result.plain == "Jane Doe (she/her)"
    assert "\\(" not in result.plain
    assert "\\)" not in result.plain


@pytest.mark.parametrize("payload_key", list(_ATTACK_PAYLOADS.keys()))
def test_untrusted_plain_in_full_pipeline_blocks_all_attacks(payload_key):
    payload = _ATTACK_PAYLOADS[payload_key]
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    context = {"name": p.render({"user": payload})}

    rendered = _full_html_pipeline("Hi {name}, welcome!", context)
    _assert_no_misleading_phish_link(rendered)
    assert '<a href="https://phish.com"' not in rendered, (
        f"HTML pipeline autolinked phish URL for payload {payload!r}: {rendered!r}"
    )

    fallback = _edited_draft_pipeline("Hi {name}, welcome!", context)
    _assert_no_misleading_phish_link(fallback, allow_bare_url_autolink=True)


def test_untrusted_plain_bare_url_is_not_autolinked_in_html_pipeline():
    # The <span> fence puts user content into MAIL_BODY_CLEANER's
    # skip_tags; organiser-typed URLs in surrounding template text are
    # still autolinked, verifying the skip is scoped to user content.
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    context = {"name": p.render({"user": "Visit https://phish.com now"})}
    rendered = _full_html_pipeline(
        "Hi {name} — see https://example.com for more.", context
    )
    assert '<a href="https://phish.com"' not in rendered
    assert '<a href="https://example.com"' in rendered


def test_untrusted_plain_repr():
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")
    assert repr(p) == "UntrustedPlainMailTextPlaceholder(name)"


def test_untrusted_markdown_plain_variant_is_stripped_plain_text():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    result = p.render({"user": "**bold** and _italic_ and `code`"})
    assert "**" not in result.plain
    assert "bold" in result.plain
    assert "italic" in result.plain
    assert "code" in result.plain


def test_untrusted_markdown_plain_variant_strips_link_syntax():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    result = p.render({"user": _ATTACK_PAYLOADS["md_link"]})
    assert "Click here" in result.plain
    assert "phish.com" not in result.plain
    assert "[" not in result.plain


def test_untrusted_markdown_html_variant_preserves_formatting():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    result = p.render({"user": "**bold** and _italic_"})
    assert "<strong>bold</strong>" in result.html
    assert "<em>italic</em>" in result.html


def test_untrusted_markdown_html_variant_strips_a_tags():
    # NO_LINKS_CLEANER excludes <a>; link text survives.
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    result = p.render({"user": _ATTACK_PAYLOADS["md_link"]})
    assert "<a" not in result.html
    assert "Click here" in result.html


def test_untrusted_markdown_html_wraps_in_div():
    # <div> wrapper = MAIL_BODY_CLEANER skip_tags fence, preventing the
    # outer mail-body renderer from re-linkifying user-typed URLs.
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    result = p.render({"user": "hello"})
    assert result.html.startswith("<div>")
    assert result.html.endswith("</div>")


def test_untrusted_markdown_handles_empty_and_none():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    assert p.render({"user": ""}).plain == ""
    assert p.render({"user": ""}).html == "<div></div>"
    assert p.render({"user": None}).plain == ""
    assert p.render({"user": None}).html == "<div></div>"


@pytest.mark.parametrize("payload_key", list(_ATTACK_PAYLOADS.keys()))
def test_untrusted_markdown_in_full_pipeline_blocks_all_attacks(payload_key):
    payload = _ATTACK_PAYLOADS[payload_key]
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    context = {"bio": p.render({"user": payload})}

    rendered = _full_html_pipeline("Speaker bio:\n\n{bio}\n\nEnd.", context)
    _assert_no_misleading_phish_link(rendered)
    assert '<a href="https://phish.com"' not in rendered, (
        f"HTML pipeline autolinked phish URL for payload {payload!r}: {rendered!r}"
    )

    fallback = _edited_draft_pipeline("Speaker bio:\n\n{bio}\n\nEnd.", context)
    _assert_no_misleading_phish_link(fallback, allow_bare_url_autolink=True)


def test_untrusted_markdown_bare_url_is_not_autolinked_in_html_pipeline():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    context = {"bio": p.render({"user": "Visit https://phish.com now"})}
    rendered = _full_html_pipeline(
        "Bio:\n\n{bio}\n\nSee https://example.com for more.", context
    )
    assert '<a href="https://phish.com"' not in rendered
    assert '<a href="https://example.com"' in rendered


def test_untrusted_markdown_repr():
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )
    assert repr(p) == "UntrustedMarkdownMailTextPlaceholder(bio)"


def test_all_untrusted_classes_return_email_alternative_strings():
    # Trust contract: untrusted placeholders MUST return
    # EmailAlternativeString so SafeFormatter picks per-mode output.
    # A plain string would get only HTML-escape with no markdown
    # neutralisation, reopening the CVE.
    up = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: "v", "sample")
    um = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: "v", "sample"
    )
    assert isinstance(up.render({"user": "v"}), EmailAlternativeString)
    assert isinstance(um.render({"user": "v"}), EmailAlternativeString)
