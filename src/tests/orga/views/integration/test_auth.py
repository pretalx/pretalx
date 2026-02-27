import datetime as dt

import pytest
from django.core import mail as djmail
from django.urls import reverse
from django.utils.timezone import now

from tests.factories import UserFactory
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.fixture
def user_with_password():
    return UserFactory(password="testpassword!")


@pytest.mark.django_db
def test_login_view_successful_login(client, user_with_password):
    """Successful orga login redirects to the event list."""
    response = client.post(
        reverse("orga:login"),
        {"login_email": user_with_password.email, "login_password": "testpassword!"},
        follow=True,
    )

    assert response.redirect_chain[-1][0] == "/orga/event/"
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_view_redirects_authenticated_user(client, user_with_password):
    """Already-authenticated user is redirected away from login page."""
    client.force_login(user_with_password)

    response = client.get(reverse("orga:login"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_login_view_preserves_next_param(client, event):
    """Login preserves ?next= parameter and redirects there after login."""
    user = make_orga_user(event)
    user.set_password("orgapass1!")
    user.save()

    next_url = event.orga_urls.base
    login_url = reverse("orga:login") + f"?next={next_url}"

    response = client.post(
        login_url,
        {"login_email": user.email, "login_password": "orgapass1!"},
        follow=True,
    )

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == next_url


@pytest.mark.django_db
def test_login_view_event_specific_redirects_to_event(client, event):
    """Login on an event-specific orga login page redirects to that event."""
    user = make_orga_user(event)
    user.set_password("orgapass1!")
    user.save()

    response = client.post(
        f"/orga/event/{event.slug}/login/",
        {"login_email": user.email, "login_password": "orgapass1!"},
    )

    assert response.status_code == 302
    assert response.url == f"/orga/event/{event.slug}/"


@pytest.mark.django_db
def test_logout_view_post_logs_out(client, user_with_password):
    """POST to logout clears the session."""
    client.force_login(user_with_password)

    response = client.post(reverse("orga:logout"))

    assert response.status_code == 302
    # Verify user is logged out by checking login page doesn't redirect
    login_response = client.get(reverse("orga:login"))
    assert login_response.status_code == 200


@pytest.mark.django_db
def test_logout_view_get_does_not_log_out(client, user_with_password):
    """GET to logout does NOT clear the session — only POST does."""
    client.force_login(user_with_password)

    response = client.get(reverse("orga:logout"))

    assert response.status_code == 302
    # User is still logged in — login page still redirects
    login_response = client.get(reverse("orga:login"))
    assert login_response.status_code == 302


@pytest.mark.django_db
def test_reset_view_sends_email(client, user_with_password):
    """Posting a valid email triggers a password reset email."""
    djmail.outbox = []

    response = client.post(
        reverse("orga:auth.reset"), {"login_email": user_with_password.email}
    )

    assert response.status_code == 302
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is not None
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_reset_view_blocks_repeated_reset_within_24h(client, user_with_password):
    """A second reset within 24 hours does not send a new email."""
    user_with_password.pw_reset_token = "existingtoken"
    user_with_password.pw_reset_time = now() - dt.timedelta(hours=1)
    user_with_password.save()
    djmail.outbox = []

    response = client.post(
        reverse("orga:auth.reset"), {"login_email": user_with_password.email}
    )

    assert response.status_code == 302
    assert len(djmail.outbox) == 0
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token == "existingtoken"


@pytest.mark.django_db
def test_reset_view_nonexistent_email_shows_success(client):
    """Posting a non-existent email still redirects (no info leak)."""
    djmail.outbox = []

    response = client.post(
        reverse("orga:auth.reset"), {"login_email": "nobody@example.com"}
    )

    assert response.status_code == 302
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_recover_view_sets_new_password(client, user_with_password):
    """Posting valid matching passwords resets the password."""
    user_with_password.pw_reset_token = "validtoken123"
    user_with_password.pw_reset_time = now()
    user_with_password.save()

    response = client.post(
        f"/orga/reset/{user_with_password.pw_reset_token}",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:login")
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is None
    assert user_with_password.check_password("mynewpassword1!")


@pytest.mark.django_db
def test_recover_view_invalid_token_redirects_to_reset(client):
    """An invalid token redirects to the reset page."""
    response = client.post(
        "/orga/reset/bogustoken",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")


@pytest.mark.django_db
def test_recover_view_expired_token_redirects_to_reset(client, user_with_password):
    """An expired token (older than 24h) redirects to the reset page."""
    user_with_password.pw_reset_token = "expiredtoken"
    user_with_password.pw_reset_time = now() - dt.timedelta(days=2)
    user_with_password.save()

    response = client.get(f"/orga/reset/{user_with_password.pw_reset_token}")

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")


@pytest.mark.parametrize(
    ("password", "password_repeat"),
    (("mynewpassword1!", "differentpassword1!"), ("password", "password")),
    ids=["mismatched", "insecure"],
)
@pytest.mark.django_db
def test_recover_view_invalid_password_keeps_token(
    client, user_with_password, password, password_repeat
):
    """Invalid passwords (mismatched or too weak) don't consume the reset token."""
    user_with_password.pw_reset_token = "validtoken123"
    user_with_password.pw_reset_time = now()
    user_with_password.save()

    response = client.post(
        f"/orga/reset/{user_with_password.pw_reset_token}",
        {"password": password, "password_repeat": password_repeat},
    )

    assert response.status_code == 200
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token == "validtoken123"


@pytest.mark.django_db
def test_reset_view_event_specific_redirects_to_event_login(client, event):
    """Event-specific reset redirects to the event login page."""
    url = reverse("orga:event.auth.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    expected = reverse("orga:event.login", kwargs={"event": event.slug})
    assert response.url == expected
