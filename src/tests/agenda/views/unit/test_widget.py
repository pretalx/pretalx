# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ImproperlyConfigured
from django_scopes import scope

import pretalx.agenda.views.widget as widget_module
from pretalx.agenda.views.widget import (
    is_public_and_versioned,
    style_etag,
    version_prefix,
    widget_js_etag,
)
from pretalx.schedule.domain.release import freeze_schedule
from tests.factories import EventFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_style_etag_is_style_version(event):
    request = make_request(event)

    result = style_etag(request, event)

    assert result == event.style_version


def test_widget_js_etag_returns_stable_checksum(event, django_assert_num_queries):
    widget_module.WIDGET_JS_CHECKSUM = None
    widget_module.WIDGET_JS_CONTENT = None

    request = make_request(event)

    with django_assert_num_queries(0):
        first = widget_js_etag(request)
        second = widget_js_etag(request)

    assert len(first) == 32  # MD5 hex digest length
    assert first == second


def test_widget_js_etag_missing_bundle_raises(event, monkeypatch):
    widget_module.WIDGET_JS_CHECKSUM = None
    widget_module.WIDGET_JS_CONTENT = None
    monkeypatch.setattr(widget_module.finders, "find", lambda path: None)

    with pytest.raises(ImproperlyConfigured, match="just npm build:wc"):
        widget_js_etag(make_request(event))


@pytest.mark.parametrize("version", (None, "wip"), ids=["unreleased", "wip"])
def test_is_public_and_versioned_false_without_public_schedule(event, version):
    request = make_request(event)

    with scope(event=event):
        result = is_public_and_versioned(request, event, version=version)

    assert result is False


@pytest.mark.parametrize("version", (None, "v1"), ids=["current", "explicit"])
def test_is_public_and_versioned_true_for_released_schedule(
    event, version, django_assert_num_queries
):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")
    request = make_request(event)

    with scope(event=event), django_assert_num_queries(1):
        result = is_public_and_versioned(request, event, version=version)

    assert result is True


def test_is_public_and_versioned_widget_always_visible():
    event = EventFactory(feature_flags={"show_widget_if_not_public": True})
    request = make_request(event)

    with scope(event=event):
        result = is_public_and_versioned(request, event)

    assert result is True


def test_version_prefix_returns_current_schedule_version(
    event, django_assert_num_queries
):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")
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
