from urllib.parse import parse_qs, urlparse

import pytest
from django.http import QueryDict
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.cfp.views.event import (
    EventCfP,
    EventPageMixin,
    EventStartpage,
    GeneralView,
    LoggedInEventPageMixin,
)
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmitterAccessCodeFactory,
    UserFactory,
)
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_event_page_mixin_get_permission_object_returns_event(event):
    request = make_request(event)
    view = make_view(EventPageMixin, request)

    assert view.get_permission_object() is event


@pytest.mark.django_db
def test_event_page_mixin_get_permission_object_returns_none_without_event(event):
    request = make_request(event)
    del request.event
    view = make_view(EventPageMixin, request)

    assert view.get_permission_object() is None


@pytest.mark.django_db
def test_logged_in_event_page_mixin_get_login_url(event):
    request = make_request(event)
    view = make_view(LoggedInEventPageMixin, request)

    expected = reverse("cfp:event.login", kwargs={"event": event.slug})
    assert view.get_login_url() == expected


@pytest.mark.django_db
def test_event_startpage_has_submissions_false_for_anonymous(event):
    request = make_request(event)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.has_submissions() is False


@pytest.mark.django_db
def test_event_startpage_has_submissions_true_when_speaker_has_talks(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    request = make_request(event, user=speaker.user)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.has_submissions() is True


@pytest.mark.django_db
def test_event_startpage_has_submissions_false_when_no_talks(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.has_submissions() is False


@pytest.mark.django_db
def test_event_startpage_has_featured_true_when_featured_exists(event):
    with scopes_disabled():
        SubmissionFactory(event=event, is_featured=True)
    request = make_request(event)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.has_featured() is True


@pytest.mark.django_db
def test_event_startpage_has_featured_false_when_none(event):
    request = make_request(event)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.has_featured() is False


@pytest.mark.django_db
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
    """submit_qs forwards only track, submission_type, and access_code query params."""
    request = make_request(event)
    qd = QueryDict(mutable=True)
    for k, v in query_params.items():
        qd[k] = v
    request.GET = qd
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        result = view.submit_qs()
    if expected_qs:
        assert parse_qs(urlparse("http://x" + result).query) == parse_qs(
            urlparse("http://x" + expected_qs).query
        )
    else:
        assert result == ""


@pytest.mark.django_db
def test_event_startpage_access_code_returns_code_when_valid(event):
    with scopes_disabled():
        access_code = SubmitterAccessCodeFactory(event=event)

    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["access_code"] = access_code.code
    request.GET = qd
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.access_code() == access_code


@pytest.mark.django_db
def test_event_startpage_access_code_returns_none_when_invalid(event):
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["access_code"] = "nonexistentcode"
    request.GET = qd
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.access_code() is None


@pytest.mark.django_db
def test_event_startpage_access_code_returns_none_when_no_param(event):
    request = make_request(event)
    view = make_view(EventStartpage, request)

    with scopes_disabled():
        assert view.access_code() is None


@pytest.mark.django_db
def test_event_cfp_has_featured_true(event):
    with scopes_disabled():
        SubmissionFactory(event=event, is_featured=True)
    request = make_request(event)
    view = make_view(EventCfP, request)

    with scopes_disabled():
        assert view.has_featured() is True


@pytest.mark.django_db
def test_event_cfp_has_featured_false(event):
    request = make_request(event)
    view = make_view(EventCfP, request)

    with scopes_disabled():
        assert view.has_featured() is False


@pytest.mark.django_db
def test_general_view_custom_domain_filters_events(event):
    """GeneralView filters events by custom_domain when uses_custom_domain is True."""
    with scopes_disabled():
        custom_event = EventFactory(
            is_public=True, custom_domain="https://custom.example.com"
        )
        no_domain_event = EventFactory(is_public=True, custom_domain=None)
    request = make_request(event)
    request.uses_custom_domain = True
    request.host = "custom.example.com"
    view = make_view(GeneralView, request)

    context = view.get_context_data()

    all_events = (
        context["current_events"] + context["past_events"] + context["future_events"]
    )
    assert custom_event in all_events
    assert no_domain_event not in all_events
