import pytest
from django.conf import settings
from django.urls import reverse

from tests.factories import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_locale_set_redirects_and_sets_cookie(client, event):
    """GET locale/set with valid locale redirects and sets language cookie."""
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=de")

    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"


@pytest.mark.django_db
def test_locale_set_invalid_locale_no_cookie(client, event):
    """GET locale/set with invalid locale redirects but doesn't set cookie."""
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=xx_INVALID")

    assert response.status_code == 302
    assert settings.LANGUAGE_COOKIE_NAME not in response.cookies


@pytest.mark.django_db
def test_locale_set_persists_for_authenticated_user(client, event):
    """Authenticated user's locale is saved to the database."""
    user = UserFactory(locale="en")
    client.force_login(user)
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    client.get(f"{url}?locale=de")

    user.refresh_from_db()
    assert user.locale == "de"


@pytest.mark.django_db
def test_locale_set_with_next_param(client, event):
    """Locale set with a next parameter redirects to that URL."""
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=en&next=/{event.slug}/cfp")

    assert response.status_code == 302
    assert f"/{event.slug}/cfp" in response.url


@pytest.mark.django_db
def test_locale_set_global_endpoint(client):
    """The global locale/set endpoint (outside event context) also works."""
    response = client.get("/locale/set?locale=de")

    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"
