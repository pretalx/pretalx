# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from urllib.parse import parse_qs, urlparse

import pytest
from django.http import QueryDict
from django.utils.timezone import now

from pretalx.cfp.views.event import EventStartpage, GeneralView
from pretalx.event.models import Event
from tests.factories import EventFactory, SubmissionFactory, SubmitterAccessCodeFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_startpage_has_featured_true_when_featured_exists(event):
    SubmissionFactory(event=event, is_featured=True)
    request = make_request(event)
    view = make_view(EventStartpage, request)

    assert view.has_featured() is True


def test_event_startpage_has_featured_false_when_none(event):
    request = make_request(event)
    view = make_view(EventStartpage, request)

    assert view.has_featured() is False


@pytest.mark.parametrize(
    ("query_params", "expected_qs"),
    (
        ({}, ""),
        ({"track": "main"}, "?track=main"),
        ({"submission_type": "talk"}, "?submission_type=talk"),
        ({"access_code": "abc123"}, "?access_code=abc123"),
        (
            {"track": "main", "submission_type": "talk"},
            "?track=main&submission_type=talk",
        ),
        ({"unrelated": "param"}, ""),
    ),
)
def test_event_startpage_submit_qs(event, query_params, expected_qs):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    for k, v in query_params.items():
        qd[k] = v
    request.GET = qd
    view = make_view(EventStartpage, request)

    result = view.submit_qs()
    if expected_qs:
        assert parse_qs(urlparse("http://x" + result).query) == parse_qs(
            urlparse("http://x" + expected_qs).query
        )
    else:
        assert result == ""


def test_event_startpage_access_code_returns_code_when_valid(event):
    access_code = SubmitterAccessCodeFactory(event=event)

    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["access_code"] = access_code.code
    request.GET = qd
    view = make_view(EventStartpage, request)

    assert view.access_code == access_code


def test_event_startpage_access_code_returns_none_when_invalid(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["access_code"] = "nonexistentcode"
    request.GET = qd
    view = make_view(EventStartpage, request)

    assert view.access_code is None


def test_event_startpage_access_code_returns_none_when_no_param(event):
    request = make_request(event)
    view = make_view(EventStartpage, request)

    assert view.access_code is None


@pytest.mark.parametrize(
    ("requires_access_code", "expected"),
    ((False, True), (True, False)),
    ids=["cfp_usable", "all_types_restricted"],
)
def test_event_startpage_can_submit_without_access_code(
    event, requires_access_code, expected
):
    event.submission_types.update(requires_access_code=requires_access_code)
    request = make_request(event)
    view = make_view(EventStartpage, request)

    assert view.can_submit() is expected


@pytest.mark.parametrize(
    ("valid_until_offset", "expected"),
    ((dt.timedelta(hours=1), True), (dt.timedelta(hours=-1), False)),
    ids=["valid", "expired"],
)
def test_event_startpage_can_submit_with_access_code(
    event, valid_until_offset, expected
):
    event.submission_types.update(requires_access_code=True)
    access_code = SubmitterAccessCodeFactory(
        event=event, valid_until=now() + valid_until_offset
    )
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["access_code"] = access_code.code
    request.GET = qd
    view = make_view(EventStartpage, request)

    assert view.can_submit() is expected


def test_general_view_custom_domain_filters_events(event):
    custom_event = EventFactory(
        is_public=True, custom_domain="https://custom.example.com"
    )
    EventFactory(is_public=True, custom_domain=None)
    request = make_request(event)
    request.uses_custom_domain = True
    request.host = "custom.example.com"
    request.custom_domain_events = Event.objects.filter(pk=custom_event.pk)
    view = make_view(GeneralView, request)

    context = view.get_context_data()

    all_events = (
        context["current_events"] + context["past_events"] + context["future_events"]
    )
    assert all_events == [custom_event]
