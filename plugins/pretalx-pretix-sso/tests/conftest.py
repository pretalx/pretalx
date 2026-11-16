import datetime as dt
import logging
from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.cache import SessionStore
from django.core.cache import cache
from django.test import RequestFactory
from django_scopes import scopes_disabled


@pytest.fixture(autouse=True)
def _plugin_logs_reach_caplog(caplog):
    # The plugin logger does not propagate to the root logger (see log.py),
    # where caplog listens, so attach caplog to it directly
    plugin_logger = logging.getLogger("pretalx_pretix_sso")
    plugin_logger.addHandler(caplog.handler)
    yield
    plugin_logger.removeHandler(caplog.handler)


@pytest.fixture(autouse=True)
def _isolation(db):
    cache.clear()
    with scopes_disabled():
        yield


@pytest.fixture
def event():
    from pretalx.event.domain.event import create_event
    from pretalx.event.domain.plugins import enable_plugin
    from pretalx.event.models import Organiser

    organiser = Organiser.objects.create(name="Org", slug="org")
    today = dt.date.today()
    # create_event also sets up the CfP, which the login and wizard pages need
    event = create_event(
        organiser=organiser,
        locales=["en"],
        name="Test",
        slug="test",
        date_from=today,
        date_to=today,
        email="orga@example.invalid",
    )
    enable_plugin(event, "pretalx_pretix_sso")
    return event


@pytest.fixture
def admin():
    from pretalx.person.models import User

    user = User.objects.create_user(
        email="admin@example.invalid", password="admin-pw", name="Admin"
    )
    user.is_administrator = True
    user.save()
    return user


@pytest.fixture
def make_speaker(event):
    from pretalx.person.models import SpeakerProfile, User

    def make(email, password=None, name="Speaker"):
        user = User.objects.create_user(email=email, password=password, name=name)
        SpeakerProfile.objects.create(user=user, event=event)
        return user

    return make


@pytest.fixture
def make_proposal(event):
    from pretalx.submission.models import Submission

    def make(title, state, *speakers):
        """``speakers`` are users; proposals list their event speaker profiles."""
        submission = Submission.objects.create(
            event=event,
            title=title,
            state=state,
            submission_type=event.cfp.default_type,
        )
        submission.speakers.add(*(user.get_speaker(event=event) for user in speakers))
        return submission

    return make


def _prepare(request, user=None, event=None):
    request.user = user or AnonymousUser()
    if event is not None:
        request.event = event
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


@pytest.fixture
def sso_callback(event):
    """Run the SSO callback as if pretix returned ``userinfo``."""
    from pretalx_pretix_sso import views

    def run(userinfo, state="st", session_state="st", next_url=""):
        request = RequestFactory().get(
            "/p/pretix-sso/callback/", {"state": state, "code": "code"}
        )
        _prepare(request)
        request.session[views.SESSION_KEY] = {
            "state": session_state,
            "nonce": "nonce",
            "verifier": "verifier",
            "event": event.slug,
            "next": next_url,
        }
        with mock.patch.object(
            views.oidc, "fetch_userinfo", return_value=userinfo
        ) as fetch:
            response = views.CallbackView.as_view()(request)
        request.fetch = fetch
        return response, request

    return run


@pytest.fixture
def tickets_page(event, admin):
    """Call the organiser tickets page; returns (response, messages)."""
    from pretalx_pretix_sso import orga_views

    def call(method="get", query="", data=None, user=None):
        path = f"/orga/event/{event.slug}/p/pretix-tickets/{query}"
        factory = RequestFactory()
        request = factory.post(path, data or {}) if method == "post" else factory.get(path)
        _prepare(request, user=user or admin, event=event)
        response = orga_views.TicketCheckView.as_view()(request, event=event.slug)
        if hasattr(response, "render"):
            response.render()
        return response, [str(m) for m in request._messages]

    return call
