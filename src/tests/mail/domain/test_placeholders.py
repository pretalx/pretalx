# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re

import pytest
from django.utils.safestring import SafeString
from i18nfield.strings import LazyI18nString

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
from pretalx.mail.domain.placeholders import (
    LinkMailTextPlaceholder,
    TrustedMarkdownMailTextPlaceholder,
    TrustedPlainMailTextPlaceholder,
    UntrustedMarkdownMailTextPlaceholder,
    UntrustedPlainMailTextPlaceholder,
    get_available_placeholders,
    get_invalid_placeholders,
    get_used_placeholders,
    placeholders_for_template,
)
from pretalx.mail.models import MailTemplate
from tests.factories import MailTemplateFactory

pytestmark = pytest.mark.unit


def _full_html_pipeline(template, context):
    # Mirror delivery_html's text_html path.
    html = format_map(template, context, mode=MODE_HTML)
    return render_mail_body(html)


def _edited_draft_pipeline(template, context):
    # Mirror delivery_html's fallback when text_html is None.
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


def test_trusted_plain_renders_required_keys_verbatim():
    p = TrustedPlainMailTextPlaceholder(
        "greeting",
        ["name", "event"],
        lambda name, event: f"Hello {name} at {event}",
        "sample",
    )

    result = p.render({"name": "Alice", "event": "PyCon", "extra": "ignored"})

    assert result == "Hello Alice at PyCon"
    assert not isinstance(result, EmailAlternativeString)


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


def test_link_placeholder_renders_dual_payload_with_safe_html():
    # SafeString bypasses conditional_escape so the downstream linkifier
    # sees raw ``&`` in query strings, not ``&amp;``.
    p = LinkMailTextPlaceholder(
        "some_url",
        ["event", "user"],
        lambda event, user: f"https://foo.test/{event}?a=1&b=2",
        "https://sample",
        is_visible=False,
    )

    result = p.render({"event": "demo", "user": object()})

    assert isinstance(result, EmailAlternativeString)
    assert result.plain == "https://foo.test/demo?a=1&b=2"
    assert result.html == "https://foo.test/demo?a=1&b=2"
    assert isinstance(result.html, SafeString)
    assert p.required_context == ["event", "user"]
    assert p.is_visible is False


def test_trusted_markdown_keeps_source_as_plain_and_compiles_links_in_html():
    # Trusted markdown is explicitly allowed to produce live links.
    p = TrustedMarkdownMailTextPlaceholder(
        "notes",
        ["event"],
        lambda event: "- first\n- Visit [pretalx](https://pretalx.com)",
        "sample",
    )

    result = p.render({"event": object()})

    assert isinstance(result, EmailAlternativeString)
    assert result.plain == "- first\n- Visit [pretalx](https://pretalx.com)"
    assert isinstance(result.html, SafeString)
    assert '<a href="https://pretalx.com"' in result.html


@pytest.mark.parametrize(
    ("value", "expected_plain", "expected_html"),
    (
        ("Jane Doe", "Jane Doe", "<span>Jane Doe</span>"),
        ("J.R.R. Tolkien", "J.R.R. Tolkien", "<span>J.R.R. Tolkien</span>"),
        ("Jean-Luc Picard", "Jean-Luc Picard", "<span>Jean-Luc Picard</span>"),
        # Only ``[`` and ``]`` are escaped, so pronouns etc. stay clean.
        ("Jane Doe (she/her)", "Jane Doe (she/her)", "<span>Jane Doe (she/her)</span>"),
        ("María-José", "María-José", "<span>María-José</span>"),
        (None, "", "<span></span>"),
        # Stripping tags in the plain variant defuses the edited-draft
        # fallback: the markdown pipeline cannot re-HTML-ify what is no
        # longer there. The HTML variant escapes inside the <span> fence.
        (
            _ATTACK_PAYLOADS["html_cve"],
            "user,We have detected suspicious activity. Click here to secure your account.",
            (
                "<span>user,&lt;br&gt;We have detected suspicious activity. "
                "&lt;a href=&quot;https://phish.com&quot;&gt;Click here to secure your account."
                "&lt;/a a=&quot;&gt;</span>"
            ),
        ),
        # Backslash-escaping ``[`` alone defangs inline, reference, and
        # image syntax in the plain variant. HTML mode uses &#91;/&#93;
        # entities instead: entities survive the second markdown pass in
        # render_mail_body, while backslashes are consumed on the first
        # pass and leave a bare ``[`` for the second one to parse as a link.
        (
            _ATTACK_PAYLOADS["md_link"],
            r"\[Click here\](https://phish.com)",
            "<span>&#91;Click here&#93;(https://phish.com)</span>",
        ),
        # Newlines collapse to <br>, otherwise markdown's paragraph
        # splitter breaks the <span> fence apart and leaks trailing
        # content to the autolinker.
        (
            _ATTACK_PAYLOADS["blank_line_bare_url"],
            "innocent\n\nhttps://phish.com\n\nhi",
            "<span>innocent<br><br>https://phish.com<br><br>hi</span>",
        ),
    ),
    ids=(
        "name",
        "initials",
        "hyphen",
        "pronouns",
        "diacritics",
        "none",
        "html_cve",
        "md_link",
        "blank_lines",
    ),
)
def test_untrusted_plain_render(value, expected_plain, expected_html):
    p = UntrustedPlainMailTextPlaceholder("name", ["user"], lambda user: user, "Jane")

    result = p.render({"user": value})

    # Trust contract: untrusted placeholders MUST return
    # EmailAlternativeString so SafeFormatter picks per-mode output.
    # A plain string would get only HTML-escape with no markdown
    # neutralisation, reopening the CVE.
    assert isinstance(result, EmailAlternativeString)
    assert result.plain == expected_plain
    assert result.html == expected_html


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


@pytest.mark.parametrize(
    ("value", "expected_plain", "expected_html"),
    (
        (
            "**bold** and _italic_ and `code`",
            "bold and italic and code",
            "<div><p><strong>bold</strong> and <em>italic</em> and <code>code</code></p></div>",
        ),
        # NO_LINKS_CLEANER excludes <a>; link text survives.
        (_ATTACK_PAYLOADS["md_link"], "Click here", "<div><p>Click here</p></div>"),
        # <div> wrapper = MAIL_BODY_CLEANER skip_tags fence, preventing the
        # outer mail-body renderer from re-linkifying user-typed URLs.
        ("hello", "hello", "<div><p>hello</p></div>"),
        ("", "", "<div></div>"),
        (None, "", "<div></div>"),
    ),
    ids=("formatting", "md_link", "plain_word", "empty", "none"),
)
def test_untrusted_markdown_render(value, expected_plain, expected_html):
    p = UntrustedMarkdownMailTextPlaceholder(
        "bio", ["user"], lambda user: user, "sample"
    )

    result = p.render({"user": value})

    assert isinstance(result, EmailAlternativeString)
    assert result.plain == expected_plain
    assert result.html == expected_html


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


@pytest.mark.parametrize(
    ("kwargs", "expected_present", "expected_absent"),
    (
        (["event"], {"event_name"}, {"name", "proposal_title"}),
        (["event", "user"], {"event_name", "name", "email"}, {"proposal_title"}),
        (
            ["event", "submission"],
            {"event_name", "proposal_title", "proposal_code"},
            {"name"},
        ),
    ),
)
@pytest.mark.django_db
def test_get_available_placeholders_filters_by_context(
    event, kwargs, expected_present, expected_absent
):
    placeholders = get_available_placeholders(event, kwargs)

    assert expected_present <= set(placeholders)
    assert expected_absent.isdisjoint(placeholders)
    assert isinstance(placeholders["event_name"], TrustedPlainMailTextPlaceholder)


@pytest.mark.django_db
def test_placeholders_for_template_without_role(event):
    template = MailTemplateFactory(event=event, role=None)

    placeholders = placeholders_for_template(template)

    assert "event_name" in placeholders
    assert "proposal_title" in placeholders


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "expected_placeholders"),
    (
        ("question.reminder", {"questions", "url"}),
        ("speaker.invite", {"invitation_link"}),
        ("submission.new.internal", {"orga_url"}),
    ),
)
def test_placeholders_for_template_includes_role_specific(
    event, role, expected_placeholders
):
    template = MailTemplate.objects.get(event=event, role=role)

    placeholders = placeholders_for_template(template)

    assert expected_placeholders <= set(placeholders)


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("", set()),
        (None, set()),
        (42, set()),
        (["{name}"], set()),
        ("No placeholders here", set()),
        ("{name}", {"name"}),
        ("{name} and {email}", {"name", "email"}),
        ("{name} and {name}", {"name"}),
        ("Hello {event_name}, welcome to {event_slug}!", {"event_name", "event_slug"}),
        (
            {"en": "Hello {name}", "de": "Hallo {name} bei {event_name}"},
            {"name", "event_name"},
        ),
        ({"en": "Hello {name}", "de": ""}, {"name"}),
        (
            LazyI18nString({"en": "{code}", "de": "{code} - {event_name}"}),
            {"code", "event_name"},
        ),
    ),
)
def test_get_used_placeholders(text, expected):
    assert get_used_placeholders(text) == expected


@pytest.mark.parametrize(
    ("text", "valid", "expected"),
    (
        ("Hello {name}", ["name", "email"], set()),
        ("Hello {name} and {bogus}", ["name"], {"bogus"}),
        ("No placeholders", ["name"], set()),
        ("{a} {b} {c}", ["a", "c"], {"b"}),
    ),
)
def test_get_invalid_placeholders(text, valid, expected):
    assert get_invalid_placeholders(text, valid) == expected
