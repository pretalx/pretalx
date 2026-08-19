# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django.urls import reverse

from pretalx.person.domain.verification import KIND_VERIFY, make_verification_token
from pretalx.person.enums import EmailVerificationState
from tests.factories import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PAGE_URL = reverse("orga:auth.verification")


def _unverified_user(**kwargs):
    kwargs.setdefault("password", "testpassword!")
    return UserFactory(
        email_verification_state=EmailVerificationState.UNVERIFIED, **kwargs
    )


def test_orga_verification_page_shows_address_needing_confirmation(client):
    user = _unverified_user(email="pending-orga@example.com")
    client.force_login(user)

    response = client.get(PAGE_URL)

    assert response.status_code == 200
    content = response.content.decode()
    assert "pending-orga@example.com" in content
    assert "password" in response.context["form"].fields


def test_orga_verification_page_redirects_anonymous_to_login(client):
    response = client.get(PAGE_URL)

    assert response.status_code == 302
    assert "/orga/login/" in response.url


def test_orga_verification_page_redirects_verified_user_away(client):
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    client.force_login(user)

    response = client.get(PAGE_URL)

    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")


@pytest.mark.usefixtures("locmem_cache")
def test_orga_verification_page_resend_sends_mail_with_orga_link(client):
    user = _unverified_user()
    client.force_login(user)
    djmail.outbox = []

    response = client.post(PAGE_URL, {"action": "resend"})

    assert response.status_code == 302
    assert response.url == PAGE_URL
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert "/orga/verify/" in djmail.outbox[0].body


def test_orga_verify_link_get_reachable_anonymously_without_verifying(client):
    user = _unverified_user(email="orga-prefetch@example.com")
    token = make_verification_token(user, KIND_VERIFY)

    response = client.get(reverse("orga:auth.verify", kwargs={"token": token}))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] is None
    assert response.context["target_email"] == "orga-prefetch@example.com"
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED


def test_orga_verify_link_post_verifies_anonymous_and_redirects_to_login(client):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)

    response = client.post(reverse("orga:auth.verify", kwargs={"token": token}))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == f"{reverse('orga:login')}?next={reverse('orga:event.list')}"
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_orga_verify_link_post_verifies_logged_in_user_and_redirects_to_events(client):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)
    client.force_login(user)

    response = client.post(reverse("orga:auth.verify", kwargs={"token": token}))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("orga:event.list")
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_orga_verification_page_redirects_verified_user_to_stored_destination(client):
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    client.force_login(user)
    session = client.session
    session["verification_next"] = "/orga/admin/"
    session.save()

    response = client.get(PAGE_URL)

    assert response.status_code == 302
    assert response.url == "/orga/admin/"
    assert "verification_next" not in client.session


def test_orga_verify_link_post_redirects_to_stored_destination(client):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)
    client.force_login(user)
    session = client.session
    session["verification_next"] = "/orga/admin/"
    session.save()

    response = client.post(reverse("orga:auth.verify", kwargs={"token": token}))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == "/orga/admin/"
    assert "verification_next" not in client.session
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_orga_event_scoped_verify_link_verifies_on_post(client, event):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)
    url = reverse(
        "orga:event.auth.verify", kwargs={"event": event.slug, "token": token}
    )

    get_response = client.get(url)
    post_response = client.post(url)

    user.refresh_from_db()
    assert get_response.status_code == 200
    assert post_response.status_code == 302
    assert user.email_verification_state == EmailVerificationState.VERIFIED
