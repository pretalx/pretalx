# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.utils.safestring import SafeString

from pretalx.mail.domain.placeholders import TrustedPlainMailTextPlaceholder
from pretalx.mail.domain.preview import (
    build_preview_context,
    mark_placeholder_value,
    render_preview_body,
    render_preview_subject,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def preview_context():
    return {
        "event_name": SafeString("Democon"),
        "event_url": SafeString("https://example.com/democon/"),
    }


def test_build_preview_context_escapes_samples(event):
    placeholders = {
        "event_name": TrustedPlainMailTextPlaceholder(
            "event_name",
            ["event"],
            lambda event: event.name,
            "<script>Democon</script>",
        ),
        "event_slug": TrustedPlainMailTextPlaceholder(
            "event_slug", ["event"], lambda event: event.slug, lambda event: event.slug
        ),
    }

    context = build_preview_context(placeholders, event)

    assert context == {
        "event_name": "&lt;script&gt;Democon&lt;/script&gt;",
        "event_slug": event.slug,
    }
    assert isinstance(context["event_name"], SafeString)


@pytest.mark.parametrize(
    ("template", "expected"),
    (
        ("Hello world", "<p>Hello world</p>"),
        ("Hello {event_name}!", f"<p>Hello {mark_placeholder_value('Democon')}!</p>"),
        (
            "[{event_name}]({event_url}) {event_name}",
            (
                '<p><a href="https://example.com/democon/" rel="noopener" '
                f'target="_blank">{mark_placeholder_value("Democon")}</a> '
                f"{mark_placeholder_value('Democon')}</p>"
            ),
        ),
        (
            "[label]({event_url}), {event_url}",
            (
                '<p><a href="https://example.com/democon/" rel="noopener" '
                'target="_blank">label</a>, '
                f"{mark_placeholder_value('https://example.com/democon/')}</p>"
            ),
        ),
        (
            "Our event ({event_name}) rocks",
            f"<p>Our event ({mark_placeholder_value('Democon')}) rocks</p>",
        ),
        (
            "`a {event_name} b` [label]({event_url}#x) ok",
            (
                "<p><code>a Democon b</code> "
                '<a href="https://example.com/democon/#x" rel="noopener" '
                'target="_blank">label</a> ok</p>'
            ),
        ),
        (
            "See [label]({event_name}\nThen {event_name}",
            (
                "<p>See [label](Democon<br>\n"
                f"Then {mark_placeholder_value('Democon')}</p>"
            ),
        ),
    ),
    ids=(
        "literal-text-unmarked",
        "placeholder-marked",
        "link-label-marked-but-not-target",
        "placeholder-after-closed-link-marked",
        "parentheses-without-link",
        "code-span-and-link-target-unmarked",
        "unclosed-link-target-reset-at-line-break",
    ),
)
def test_render_preview_body(template, expected, preview_context):
    assert render_preview_body(template, preview_context) == expected


def test_render_preview_subject_marks_placeholder_values(event, preview_context):
    result = render_preview_subject("Hello {event_name}", preview_context, event)

    assert result == f"Hello {mark_placeholder_value('Democon')}"


def test_render_preview_subject_marks_link_syntax(event, preview_context):
    result = render_preview_subject(
        "See [{event_name}]({event_url}) now", preview_context, event
    )

    assert result == (
        f"See [{mark_placeholder_value('Democon')}]"
        f"({mark_placeholder_value('https://example.com/democon/')}) now"
    )


def test_render_preview_subject_escapes_unsafe_values(event):
    result = render_preview_subject(
        "Hi {event_name}", {"event_name": "<b>x</b>"}, event
    )

    assert result == f"Hi {mark_placeholder_value('&lt;b&gt;x&lt;/b&gt;')}"


def test_render_preview_subject_prefixes_and_strips_markup(event, preview_context):
    event.mail_settings["subject_prefix"] = "democon"

    result = render_preview_subject("<b>Hi</b> {event_name}", preview_context, event)

    assert result == (
        f"[democon] &lt;b&gt;Hi&lt;/b&gt; {mark_placeholder_value('Democon')}"
    )
