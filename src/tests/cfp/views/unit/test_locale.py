import pytest
from django.conf import settings
from django.http import QueryDict

from pretalx.cfp.views.locale import LocaleSet
from tests.factories import UserFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_locale_set_redirects_to_root_without_next(event):
    """LocaleSet redirects to / when no 'next' parameter is set."""
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "en"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_locale_set_sets_cookie_for_valid_locale(event):
    """LocaleSet sets language cookie for a valid locale."""
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"


@pytest.mark.django_db
def test_locale_set_does_not_set_cookie_for_invalid_locale(event):
    """LocaleSet does not set a cookie for an invalid locale."""
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "xx"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)

    assert settings.LANGUAGE_COOKIE_NAME not in response.cookies


@pytest.mark.django_db
def test_locale_set_saves_locale_for_authenticated_user(event):
    """LocaleSet persists locale to user model for authenticated users."""
    user = UserFactory(locale="en")
    request = make_request(event, user=user)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    view.get(request)

    user.refresh_from_db()
    assert user.locale == "de"


@pytest.mark.django_db
def test_locale_set_does_not_save_locale_for_anonymous(event):
    """LocaleSet does not try to save locale on anonymous user."""
    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["locale"] = "de"
    request.GET = qd
    view = make_view(LocaleSet, request)

    response = view.get(request)
    assert response.status_code == 302
