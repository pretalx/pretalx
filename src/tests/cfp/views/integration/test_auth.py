import datetime as dt

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.timezone import now

from tests.factories import EventFactory, UserFactory

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")

pytestmark = pytest.mark.integration


@pytest.fixture
def public_event():
    return EventFactory(is_public=True)


@pytest.fixture
def speaker(public_event):
    return UserFactory(email="speaker@example.com", password="testpassword!")


@pytest.mark.django_db
def test_login_view_successful_login(client, public_event, speaker):
    """Successful login redirects to user submissions page."""
    url = reverse("cfp:event.login", kwargs={"event": public_event.slug})

    response = client.post(
        url, {"login_email": "speaker@example.com", "login_password": "testpassword!"}
    )

    assert response.status_code == 302
    assert public_event.urls.user_submissions in response.url


@pytest.mark.django_db
def test_login_view_incorrect_password(client, public_event, speaker):
    """Login with wrong password re-renders the form with errors."""
    url = reverse("cfp:event.login", kwargs={"event": public_event.slug})

    response = client.post(
        url, {"login_email": "speaker@example.com", "login_password": "wrongpassword!"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_login_view_nonexistent_email(client, public_event):
    """Login with non-existent email re-renders the form with errors."""
    url = reverse("cfp:event.login", kwargs={"event": public_event.slug})

    response = client.post(
        url, {"login_email": "nobody@example.com", "login_password": "testpassword!"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_login_view_redirects_authenticated_user(client, public_event, speaker):
    """Already-authenticated user is redirected to success URL."""
    client.force_login(speaker)
    url = reverse("cfp:event.login", kwargs={"event": public_event.slug})

    response = client.get(url)

    assert response.status_code == 302
    assert public_event.urls.user_submissions in response.url


@pytest.mark.django_db
def test_login_view_404_for_non_public_event(client, event):
    """Login page returns 404 when event is not public."""
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_logout_view_post_logs_out(client, public_event, speaker):
    """POST to logout clears the session and redirects to event start."""
    client.force_login(speaker)
    url = reverse("cfp:event.logout", kwargs={"event": public_event.slug})

    response = client.post(url)

    assert response.status_code == 302
    assert f"/{public_event.slug}/cfp" in response.url
    # Verify the user is actually logged out
    me_url = reverse("cfp:event.user.submissions", kwargs={"event": public_event.slug})
    me_response = client.get(me_url)
    # Logged-out user gets redirected to login
    assert me_response.status_code == 302


@pytest.mark.django_db
def test_logout_view_get_redirects_to_event_start(client, public_event, speaker):
    """GET to logout redirects to event start page."""
    client.force_login(speaker)
    url = reverse("cfp:event.logout", kwargs={"event": public_event.slug})

    response = client.get(url)

    assert response.status_code == 302
    assert f"/{public_event.slug}/cfp" in response.url


@pytest.mark.django_db
def test_reset_view_renders_form(client, public_event):
    """Reset page renders a form for entering email."""
    url = reverse("cfp:event.reset", kwargs={"event": public_event.slug})

    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_reset_view_sends_reset_email(client, public_event, speaker):
    """Posting a valid email triggers a password reset email."""
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": public_event.slug})

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    speaker.refresh_from_db()
    assert speaker.pw_reset_token is not None
    assert len(djmail.outbox) == 1
    assert "speaker@example.com" in djmail.outbox[0].to


@pytest.mark.django_db
def test_reset_view_nonexistent_email_shows_success(client, public_event):
    """Posting a non-existent email still shows success message (no info leak)."""
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": public_event.slug})

    response = client.post(url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_reset_view_blocks_repeated_reset_within_24h(client, public_event, speaker):
    """A second reset within 24 hours does not send a new email."""
    speaker.pw_reset_token = "oldtoken123"
    speaker.pw_reset_time = now() - dt.timedelta(hours=1)
    speaker.save()
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": public_event.slug})

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    assert len(djmail.outbox) == 0
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "oldtoken123"


@pytest.mark.django_db
def test_recover_view_renders_form_with_valid_token(client, public_event, speaker):
    """Recover page renders password form when token is valid."""
    speaker.pw_reset_token = "validtoken123"
    speaker.pw_reset_time = now()
    speaker.save()
    url = reverse(
        "cfp:event.recover",
        kwargs={"event": public_event.slug, "token": "validtoken123"},
    )

    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_recover_view_sets_new_password(client, public_event, speaker):
    """Posting a valid new password resets the user's password."""
    speaker.pw_reset_token = "validtoken123"
    speaker.pw_reset_time = now()
    speaker.save()
    url = reverse(
        "cfp:event.recover",
        kwargs={"event": public_event.slug, "token": "validtoken123"},
    )

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "newsecurepassword1!"},
    )

    assert response.status_code == 302
    assert "login" in response.url
    speaker.refresh_from_db()
    assert speaker.pw_reset_token is None
    assert speaker.check_password("newsecurepassword1!")


@pytest.mark.django_db
def test_recover_view_redirects_on_invalid_token(client, public_event):
    """Recover page redirects to reset when token doesn't match any user."""
    url = reverse(
        "cfp:event.recover", kwargs={"event": public_event.slug, "token": "bogustoken"}
    )

    response = client.get(url)

    assert response.status_code == 302
    assert "reset" in response.url


@pytest.mark.django_db
def test_recover_view_redirects_on_expired_token(client, public_event, speaker):
    """Recover page redirects to reset when token is expired."""
    speaker.pw_reset_token = "expiredtoken123"
    speaker.pw_reset_time = now() - dt.timedelta(days=2)
    speaker.save()
    url = reverse(
        "cfp:event.recover",
        kwargs={"event": public_event.slug, "token": "expiredtoken123"},
    )

    response = client.get(url)

    assert response.status_code == 302
    assert "reset" in response.url


@pytest.mark.django_db
def test_recover_view_rejects_mismatched_passwords(client, public_event, speaker):
    """Mismatched passwords keep the token and don't reset the password."""
    speaker.pw_reset_token = "validtoken123"
    speaker.pw_reset_time = now()
    speaker.save()
    url = reverse(
        "cfp:event.recover",
        kwargs={"event": public_event.slug, "token": "validtoken123"},
    )

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "differentpassword1!"},
    )

    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "validtoken123"


@pytest.mark.django_db
def test_recover_view_rejects_insecure_password(client, public_event, speaker):
    """Common/weak password is rejected by Django validators."""
    speaker.pw_reset_token = "validtoken123"
    speaker.pw_reset_time = now()
    speaker.save()
    url = reverse(
        "cfp:event.recover",
        kwargs={"event": public_event.slug, "token": "validtoken123"},
    )

    response = client.post(url, {"password": "password", "password_repeat": "password"})

    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "validtoken123"


@pytest.mark.django_db
def test_recover_view_as_invite_sets_context(client, public_event, speaker):
    """The invite variant of RecoverView sets is_invite_template=True in context."""
    speaker.pw_reset_token = "invitetoken123"
    speaker.pw_reset_time = now()
    speaker.save()
    url = reverse(
        "cfp:event.new_recover",
        kwargs={"event": public_event.slug, "token": "invitetoken123"},
    )

    response = client.get(url)

    assert response.status_code == 200
    assert response.context["is_invite_template"] is True


@pytest.mark.django_db
def test_full_password_reset_flow(client, public_event, speaker):
    """End-to-end: request reset, use token, login with new password."""
    djmail.outbox = []
    reset_url = reverse("cfp:event.reset", kwargs={"event": public_event.slug})
    client.post(reset_url, {"login_email": "speaker@example.com"})

    speaker.refresh_from_db()
    token = speaker.pw_reset_token
    assert token is not None

    recover_url = reverse(
        "cfp:event.recover", kwargs={"event": public_event.slug, "token": token}
    )
    client.post(
        recover_url,
        {"password": "brandnewpassword1!", "password_repeat": "brandnewpassword1!"},
    )

    login_url = reverse("cfp:event.login", kwargs={"event": public_event.slug})
    response = client.post(
        login_url,
        {"login_email": "speaker@example.com", "login_password": "brandnewpassword1!"},
    )
    assert response.status_code == 302
    assert public_event.urls.user_submissions in response.url


@pytest.mark.django_db
def test_event_auth_post_valid_session_redirects_to_event_base(client, public_event):
    """EventAuth with valid session data redirects to event base URL."""
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{public_event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": public_event.slug})
    response = client.post(url, {"session": child_store.session_key})

    assert response.status_code == 302
    assert response.url == public_event.urls.base


@pytest.mark.django_db
def test_event_auth_post_invalid_session_returns_403(client, public_event):
    """EventAuth with an invalid session key returns 403."""
    url = reverse("cfp:event.auth", kwargs={"event": public_event.slug})

    response = client.post(url, {"session": "invalidsessionkey"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_event_auth_post_missing_event_access_returns_403(client, public_event):
    """EventAuth returns 403 when parent session has no 'event_access' key."""
    parent_store = SessionStore()
    parent_store["something_else"] = True
    parent_store.create()

    key = f"pretalx_event_access_{public_event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": public_event.slug})
    response = client.post(url, {"session": child_store.session_key})

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("target", "url_part"), (("cfp", "/cfp"), ("schedule", "/schedule/"))
)
def test_event_auth_post_target_redirects_correctly(
    client, public_event, target, url_part
):
    """EventAuth redirects to CfP or schedule based on target POST param."""
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{public_event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": public_event.slug})
    response = client.post(url, {"session": child_store.session_key, "target": target})

    assert response.status_code == 302
    assert url_part in response.url


@pytest.mark.django_db
def test_event_auth_post_unknown_target_redirects_to_base(client, public_event):
    """EventAuth with an unrecognized target value falls back to event base URL."""
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{public_event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": public_event.slug})
    response = client.post(
        url, {"session": child_store.session_key, "target": "unknown"}
    )

    assert response.status_code == 302
    assert response.url == public_event.urls.base
