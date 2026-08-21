# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import re
import time

import pytest
from django.core import mail as djmail
from django.urls import reverse
from django.utils.timezone import now

from pretalx.person.domain.verification import (
    KIND_CHANGE,
    KIND_VERIFY,
    make_verification_token,
)
from pretalx.person.enums import EmailVerificationState
from tests.factories import UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _unverified_user(**kwargs):
    kwargs.setdefault("password", "testpassword!")
    return UserFactory(
        email_verification_state=EmailVerificationState.UNVERIFIED, **kwargs
    )


def _page_url(event):
    return reverse("cfp:event.verification", kwargs={"event": event.slug})


def _verify_url(event, token):
    return reverse("cfp:event.verify", kwargs={"event": event.slug, "token": token})


def test_verification_page_shows_address_needing_confirmation(client, event):
    user = _unverified_user(email="pending-speaker@example.com")
    client.force_login(user)

    response = client.get(_page_url(event))

    assert response.status_code == 200
    content = response.content.decode()
    assert "pending-speaker@example.com" in content
    assert "password" in response.context["form"].fields
    assert "email" in response.context["form"].fields
    assert "email-correction-dialog" in content
    assert not re.search(r"<dialog[^>]*\bopen", content)


def test_verification_page_redirects_anonymous_to_login(client, event):
    response = client.get(_page_url(event))

    assert response.status_code == 302
    assert f"/{event.slug}/login/" in response.url
    assert "next=" in response.url


@pytest.mark.parametrize(
    "state",
    (EmailVerificationState.VERIFIED, EmailVerificationState.LEGACY),
    ids=["verified", "legacy"],
)
def test_verification_page_redirects_proven_user_away(client, event, state):
    user = UserFactory(email_verification_state=state)
    client.force_login(user)

    response = client.get(_page_url(event))

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/me/submissions/"


@pytest.mark.parametrize("draft", (True, False))
def test_verification_page_acknowledges_submission_once(client, event, draft):
    user = _unverified_user()
    client.force_login(user)
    session = client.session
    session["verification_submission"] = {"code": "ABCDEF", "draft": draft}
    session.save()

    response = client.get(_page_url(event))
    second_response = client.get(_page_url(event))

    assert response.context["acknowledged_submission"] == {
        "code": "ABCDEF",
        "draft": draft,
    }
    assert "alert-success" in response.content.decode()
    assert second_response.context["acknowledged_submission"] is None


@pytest.mark.usefixtures("locmem_cache")
def test_verification_page_resend_sends_mail_and_sets_cooldown(client, event):
    user = _unverified_user()
    client.force_login(user)
    djmail.outbox = []

    response = client.post(_page_url(event), {"action": "resend"})
    page = client.get(_page_url(event))

    assert response.status_code == 302
    assert response.url == _page_url(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert f"/{event.slug}/verify/" in djmail.outbox[0].body
    assert page.context["cooldown"] > 0
    assert "disabled" in page.content.decode()


@pytest.mark.usefixtures("locmem_cache")
def test_verification_page_resend_within_cooldown_sends_nothing(client, event):
    user = _unverified_user()
    client.force_login(user)
    client.post(_page_url(event), {"action": "resend"}, follow=True)
    djmail.outbox = []

    response = client.post(_page_url(event), {"action": "resend"}, follow=True)

    assert djmail.outbox == []
    assert [message.level_tag for message in response.context["messages"]] == ["danger"]


def test_verification_page_wrong_address_requires_password(client, event):
    user = _unverified_user(email="typo@example.com")
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        _page_url(event), {"email": "fixed@example.com", "password": "wrongpassword!"}
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["form"].has_error("password", "pw_current_wrong")
    assert re.search(r"<dialog[^>]*\bopen", response.content.decode())
    assert user.email == "typo@example.com"
    assert djmail.outbox == []


@pytest.mark.usefixtures("locmem_cache")
def test_verification_page_wrong_address_corrects_and_kills_old_links(client, event):
    user = _unverified_user(email="typo@example.com")
    old_token = make_verification_token(user, KIND_VERIFY)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        _page_url(event), {"email": "fixed@example.com", "password": "testpassword!"}
    )
    old_link_page = client.get(_verify_url(event, old_token))

    user.refresh_from_db()
    assert response.status_code == 302
    assert user.email == "fixed@example.com"
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["fixed@example.com"]
    assert old_link_page.context["error"] == "invalid"


@pytest.mark.usefixtures("locmem_cache")
def test_verification_page_wrong_address_free_once_then_blocked_during_cooldown(
    client, event
):
    user = _unverified_user(email="typo@example.com")
    client.force_login(user)
    client.post(_page_url(event), {"action": "resend"})
    djmail.outbox = []

    free = client.post(
        _page_url(event), {"email": "fixed@example.com", "password": "testpassword!"}
    )
    blocked = client.post(
        _page_url(event), {"email": "second@example.com", "password": "testpassword!"}
    )

    user.refresh_from_db()
    assert free.status_code == 302
    assert blocked.status_code == 200
    assert blocked.context["form"].non_field_errors()
    assert user.email == "fixed@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["fixed@example.com"]


def test_verification_page_wrong_address_taken_in_race_shows_form_error(
    client, event, monkeypatch
):
    user = _unverified_user(email="typo@example.com")
    UserFactory(email="taken@example.com")
    client.force_login(user)
    djmail.outbox = []
    monkeypatch.setattr(
        "pretalx.person.interfaces.forms.auth.validate_email_unique",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        _page_url(event), {"email": "taken@example.com", "password": "testpassword!"}
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["form"].errors["email"]
    assert user.email == "typo@example.com"
    assert djmail.outbox == []


def test_verify_link_get_does_not_verify(client, event):
    user = _unverified_user(email="prefetch@example.com")
    token = make_verification_token(user, KIND_VERIFY)

    response = client.get(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] is None
    assert response.context["target_email"] == "prefetch@example.com"
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED


def test_verify_link_post_verifies_anonymous_and_redirects_to_login(client, event):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == f"/{event.slug}/login/?next=/{event.slug}/me/submissions/"
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_verify_link_post_verifies_logged_in_user_and_redirects_to_submissions(
    client, event
):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)
    client.force_login(user)

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == f"/{event.slug}/me/submissions/"
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_verify_link_post_redirects_to_stored_destination(client, event):
    user = _unverified_user()
    token = make_verification_token(user, KIND_VERIFY)
    client.force_login(user)
    session = client.session
    session["verification_next"] = f"/{event.slug}/talk/ABCDEF/#signup"
    session.save()

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == f"/{event.slug}/talk/ABCDEF/#signup"
    assert "verification_next" not in client.session
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_verification_page_redirects_proven_user_to_stored_destination(client, event):
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    client.force_login(user)
    session = client.session
    session["verification_next"] = f"/{event.slug}/talk/ABCDEF/#signup"
    session.save()

    response = client.get(_page_url(event))

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/talk/ABCDEF/#signup"
    assert "verification_next" not in client.session


@pytest.mark.parametrize("method", ("get", "post"))
def test_verify_link_expired_offers_resend(client, event, method):
    user = _unverified_user()
    real_time = time.time()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, "time", lambda: real_time - 25 * 3600)
        token = make_verification_token(user, KIND_VERIFY)

    response = getattr(client, method)(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "expired"
    assert _page_url(event) in response.content.decode()
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED


@pytest.mark.parametrize("method", ("get", "post"))
def test_verify_link_stale_after_address_change_is_invalid(client, event, method):
    user = _unverified_user(email="before@example.com")
    token = make_verification_token(user, KIND_VERIFY)
    user.email = "after@example.com"
    user.save()

    response = getattr(client, method)(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "invalid"
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED


@pytest.mark.parametrize("method", ("get", "post"))
def test_verify_link_already_verified_shows_notice_without_new_log(
    client, event, method
):
    user = UserFactory(email_verification_state=EmailVerificationState.UNVERIFIED)
    token = make_verification_token(user, KIND_VERIFY)
    client.post(_verify_url(event, token))

    response = getattr(client, method)(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "already_verified"
    assert user.email_verification_state == EmailVerificationState.VERIFIED


def test_verify_change_link_get_shows_pending_address(client, event):
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    user.pending_email = "new@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)

    response = client.get(_verify_url(event, token))

    assert response.status_code == 200
    assert response.context["error"] is None
    assert response.context["target_email"] == "new@example.com"


def test_verify_change_link_post_applies_pending_change(client, event):
    user = UserFactory(
        email="old@example.com", email_verification_state=EmailVerificationState.LEGACY
    )
    user.pending_email = "new@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)
    djmail.outbox = []

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 302
    assert user.email == "new@example.com"
    assert user.pending_email is None
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["old@example.com"]


def test_verify_change_link_expired_pending_get_shows_error_without_writes(
    client, event
):
    user = UserFactory(email_verification_state=EmailVerificationState.VERIFIED)
    user.pending_email = "new@example.com"
    user.pending_email_sent = now() - dt.timedelta(hours=25)
    user.save()
    token = make_verification_token(user, KIND_CHANGE)

    response = client.get(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "pending_expired"
    assert user.pending_email == "new@example.com"
    assert user.pending_email_sent is not None


def test_verify_change_link_expired_pending_post_clears_and_offers_rerequest(
    client, event
):
    user = UserFactory(
        email="old@example.com",
        email_verification_state=EmailVerificationState.VERIFIED,
    )
    user.pending_email = "new@example.com"
    user.pending_email_sent = now() - dt.timedelta(hours=25)
    user.save()
    token = make_verification_token(user, KIND_CHANGE)

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "pending_expired"
    assert user.email == "old@example.com"
    assert user.pending_email is None
    assert user.pending_email_sent is None


def test_verify_change_link_target_taken_shows_error(client, event):
    user = UserFactory(
        email="old@example.com",
        email_verification_state=EmailVerificationState.VERIFIED,
    )
    user.pending_email = "new@example.com"
    user.pending_email_sent = now()
    user.save()
    token = make_verification_token(user, KIND_CHANGE)
    UserFactory(email="new@example.com")

    response = client.post(_verify_url(event, token))

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.context["error"] == "taken"
    assert user.email == "old@example.com"
    assert user.pending_email is None
    assert user.pending_email_sent is None
