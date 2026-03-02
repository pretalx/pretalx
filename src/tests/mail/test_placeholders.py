# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.mail.placeholders import (
    BaseMailTextPlaceholder,
    SimpleFunctionalMailTextPlaceholder,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("attr", "expected"),
    (("required_context", ["event"]), ("is_visible", True), ("explanation", "")),
)
def test_base_placeholder_default_values(attr, expected):
    placeholder = BaseMailTextPlaceholder()
    assert getattr(placeholder, attr) == expected


def test_simple_placeholder_render_calls_func_with_context_keys():
    """render() extracts the required keys from the context dict and
    passes them as kwargs to the wrapped function, ignoring extra keys."""
    p = SimpleFunctionalMailTextPlaceholder(
        "greeting",
        ["name", "event"],
        lambda name, event: f"Hello {name} at {event}",
        "sample",
    )

    result = p.render({"name": "Alice", "event": "PyCon", "extra": "ignored"})

    assert result == "Hello Alice at PyCon"


@pytest.mark.parametrize(
    ("sample", "event_arg", "expected"),
    (
        ("Example Conference", None, "Example Conference"),
        (lambda event: f"Sample: {event}", "PyCon", "Sample: PyCon"),
    ),
)
def test_simple_placeholder_render_sample(sample, event_arg, expected):
    """Static strings are returned directly; callables are called with the event."""
    p = SimpleFunctionalMailTextPlaceholder(
        "event_name", ["event"], lambda event: event, sample
    )
    assert p.render_sample(event_arg) == expected


def test_simple_placeholder_repr():
    p = SimpleFunctionalMailTextPlaceholder(
        "event_name", ["event"], lambda event: event, "sample"
    )
    assert repr(p) == "SimpleFunctionalMailTextPlaceholder(event_name)"
