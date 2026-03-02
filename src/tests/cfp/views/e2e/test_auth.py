# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django.urls import reverse

from tests.factories import UserFactory

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def test_full_password_reset_flow(client, event):
    """End-to-end: request reset, use token, login with new password."""
    speaker = UserFactory(email="speaker@example.com", password="testpassword!")
    djmail.outbox = []
    reset_url = reverse("cfp:event.reset", kwargs={"event": event.slug})
    client.post(reset_url, {"login_email": "speaker@example.com"})

    speaker.refresh_from_db()
    token = speaker.pw_reset_token
    assert token is not None

    recover_url = reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": token}
    )
    client.post(
        recover_url,
        {"password": "brandnewpassword1!", "password_repeat": "brandnewpassword1!"},
    )

    login_url = reverse("cfp:event.login", kwargs={"event": event.slug})
    response = client.post(
        login_url,
        {"login_email": "speaker@example.com", "login_password": "brandnewpassword1!"},
    )
    assert response.status_code == 302
    assert event.urls.user_submissions in response.url
