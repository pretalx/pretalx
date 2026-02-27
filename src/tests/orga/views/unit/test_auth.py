import pytest
from django.urls import reverse

from pretalx.orga.views.auth import LoginView, RecoverView, ResetView
from tests.factories import EventFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_login_view_event_returns_request_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    assert view.event == event


@pytest.mark.django_db
def test_login_view_event_returns_none_without_event():
    """When request has no event attribute, event property returns None."""
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.event is None


@pytest.mark.django_db
def test_login_view_success_url_with_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    assert view.success_url == event.orga_urls.base


@pytest.mark.django_db
def test_login_view_success_url_without_event():
    """Without event, success_url falls back to the event list."""
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.success_url == reverse("orga:event.list")


@pytest.mark.django_db
def test_login_view_get_form_kwargs_hides_register(event):
    request = make_request(event)
    view = make_view(LoginView, request)
    view.object = None

    kwargs = view.get_form_kwargs()

    assert kwargs["hide_register"] is True


@pytest.mark.django_db
def test_login_view_get_password_reset_link_with_event(event):
    request = make_request(event)
    view = make_view(LoginView, request)

    expected = reverse("orga:event.auth.reset", kwargs={"event": event.slug})
    assert view.get_password_reset_link() == expected


@pytest.mark.django_db
def test_login_view_get_password_reset_link_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(LoginView, request)

    assert view.get_password_reset_link() == reverse("orga:auth.reset")


@pytest.mark.django_db
def test_reset_view_get_success_url_with_event(event):
    request = make_request(event)
    view = make_view(ResetView, request)

    expected = reverse("orga:event.login", kwargs={"event": event.slug})
    assert view.get_success_url() == expected


@pytest.mark.django_db
def test_reset_view_get_success_url_without_event():
    event = EventFactory()
    request = make_request(event)
    del request.event
    view = make_view(ResetView, request)

    assert view.get_success_url() == reverse("orga:login")


@pytest.mark.django_db
def test_recover_view_get_success_url():
    event = EventFactory()
    request = make_request(event)
    view = make_view(RecoverView, request)

    assert view.get_success_url() == reverse("orga:login")


@pytest.mark.django_db
def test_recover_view_get_user_finds_valid_token():
    user = UserFactory()
    user.reset_password(event=None, orga=True)
    user.refresh_from_db()
    event = EventFactory()
    request = make_request(event)
    view = make_view(RecoverView, request, token=user.pw_reset_token)

    assert view.get_user() == user
