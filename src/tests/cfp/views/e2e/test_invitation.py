# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django_scopes import scopes_disabled

from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def test_e2e_co_speaker_login_hop_sends_mail_then_promotes_at_accept(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        invitation = SubmissionInvitationFactory(
            submission=submission, email="cospeaker@example.com"
        )
    invite_url = invitation.urls.base.full()
    djmail.outbox = []

    response = client.get(invite_url)
    assert response.status_code == 302
    assert "login" in response.url

    response = client.post(
        response.url,
        {
            "register_name": "Co Speaker",
            "register_email": "cospeaker@example.com",
            "register_password": "a-very-good-password!",
            "register_password_repeat": "a-very-good-password!",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="cospeaker@example.com")
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["cospeaker@example.com"]

    response = client.post(invite_url)
    assert response.status_code == 302
    with scopes_disabled():
        assert submission.speakers.filter(user=user).exists()
    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
