import pytest
from django.http import Http404
from django.utils.timezone import now

from pretalx.cfp.views.auth import LoginView, LogoutView, RecoverView
from tests.factories import UserFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_logout_view_get_redirects_to_event_start(event):
    request = make_request(event)
    view = make_view(LogoutView, request)

    response = view.get(request)

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/cfp"


@pytest.mark.django_db
def test_login_view_dispatch_raises_404_when_event_not_public(event):
    """LoginView.dispatch raises Http404 when the event is not public."""
    event.is_public = False
    event.save()
    request = make_request(event)

    with pytest.raises(Http404):
        LoginView.as_view()(request, event=event.slug)


@pytest.mark.django_db
def test_login_view_get_error_url_returns_event_base(event):
    event.is_public = True
    event.save()
    request = make_request(event)
    view = make_view(LoginView, request, event=event.slug)

    assert view.get_error_url() == event.urls.base


@pytest.mark.django_db
def test_login_view_success_url_returns_user_submissions(event):
    event.is_public = True
    event.save()
    request = make_request(event)
    view = make_view(LoginView, request, event=event.slug)

    assert view.success_url == event.urls.user_submissions


@pytest.mark.django_db
def test_login_view_get_password_reset_link_returns_reset_url(event):
    event.is_public = True
    event.save()
    request = make_request(event)
    view = make_view(LoginView, request, event=event.slug)

    assert view.get_password_reset_link() == event.urls.reset


@pytest.mark.django_db
@pytest.mark.parametrize(("is_invite", "expected"), ((False, False), (True, True)))
def test_recover_view_is_invite_template(event, is_invite, expected):
    user = UserFactory()
    user.pw_reset_token = "validtoken123"
    user.pw_reset_time = now()
    user.save()
    request = make_request(event)
    view = make_view(RecoverView, request, token="validtoken123", event=event.slug)
    view.user = user
    view.is_invite = is_invite

    assert view.is_invite_template() is expected
