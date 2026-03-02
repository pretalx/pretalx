# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

import pretalx.agenda.views.widget as widget_module
from pretalx.agenda.views.widget import (
    color_etag,
    is_public_and_versioned,
    version_prefix,
    widget_js_etag,
)
from tests.factories import EventFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_color_etag_no_color(event):
    request = make_request(event)

    result = color_etag(request, event)

    assert result == "none"


@pytest.mark.parametrize(
    ("color", "expected"),
    (
        ("#000000", "#000000:False"),
        ("#00ff00", "#00ff00:True"),
        ("#ffffff", "#ffffff:True"),
    ),
    ids=["dark_no_dark_text", "green_needs_dark_text", "light_needs_dark_text"],
)
def test_color_etag_with_color(color, expected):
    event = EventFactory(primary_color=color)
    request = make_request(event)

    result = color_etag(request, event)

    assert result == expected


def test_widget_js_etag_returns_checksum(event, django_assert_num_queries):
    widget_module.WIDGET_JS_CHECKSUM = None
    widget_module.WIDGET_JS_CONTENT = None

    request = make_request(event)

    with django_assert_num_queries(0):
        result = widget_js_etag(request, event)

    assert result is not None
    assert len(result) == 32  # MD5 hex digest length


def test_widget_js_etag_stable_across_calls(event):
    widget_module.WIDGET_JS_CHECKSUM = None
    widget_module.WIDGET_JS_CONTENT = None

    request = make_request(event)
    first = widget_js_etag(request, event)
    second = widget_js_etag(request, event)

    assert first == second


def test_is_public_and_versioned_wip_returns_false(event):
    request = make_request(event)

    result = is_public_and_versioned(request, event, version="wip")

    assert result is False


def test_is_public_and_versioned_no_version_visible_schedule(
    event, django_assert_num_queries
):
    with scope(event=event):
        event.release_schedule("v1")
    request = make_request(event)

    with scope(event=event), django_assert_num_queries(1):
        result = is_public_and_versioned(request, event)

    assert result is True


def test_is_public_and_versioned_not_visible(event):
    request = make_request(event)

    with scope(event=event):
        result = is_public_and_versioned(request, event)

    assert result is False


def test_is_public_and_versioned_widget_always_visible():
    event = EventFactory(feature_flags={"show_widget_if_not_public": True})
    request = make_request(event)

    with scope(event=event):
        result = is_public_and_versioned(request, event)

    assert result is True


def test_is_public_and_versioned_with_version(event):
    with scope(event=event):
        event.release_schedule("v1")
    request = make_request(event)

    with scope(event=event):
        result = is_public_and_versioned(request, event, version="v1")

    assert result is True


def test_version_prefix_returns_current_schedule_version(
    event, django_assert_num_queries
):
    with scope(event=event):
        event.release_schedule("v1")
    request = make_request(event)

    with scope(event=event), django_assert_num_queries(1):
        result = version_prefix(request, event)

    assert result == "v1"


def test_version_prefix_returns_explicit_version(event, django_assert_num_queries):
    request = make_request(event)

    with django_assert_num_queries(0):
        result = version_prefix(request, event, version="v2")

    assert result == "v2"


def test_version_prefix_no_schedule_returns_none(event, django_assert_num_queries):
    request = make_request(event)

    with scope(event=event), django_assert_num_queries(1):
        result = version_prefix(request, event)

    assert result is None
