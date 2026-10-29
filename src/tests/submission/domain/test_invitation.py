# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re

import pytest
from django.core import mail as djmail
from django.db import transaction
from django_scopes import scope

from pretalx.common.exceptions import SendMailException
from pretalx.submission.domain.invitation import (
    accept_invitation,
    retract_invitation,
    send_invitation,
)
from pretalx.submission.models import SubmissionInvitation
from tests.factories import (
    EventFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_send_invitation_persists_logs_and_is_idempotent(
    django_capture_on_commit_callbacks,
):
    event = EventFactory()
    sender = UserFactory()
    submission = SubmissionFactory(event=event)
    djmail.outbox = []

    with scope(event=event):
        with django_capture_on_commit_callbacks(execute=True):
            invitation = send_invitation(
                submission, email="invitee@example.com", sender=sender, orga=True
            )

        assert invitation.pk is not None
        assert invitation.email == "invitee@example.com"
        assert [mail.to for mail in djmail.outbox] == [["invitee@example.com"]]
        log = submission.logged_actions().get(
            action_type="pretalx.submission.invitation.send"
        )
        assert log.person == sender
        assert log.is_orga_action is True
        assert log.data == {"email": "invitee@example.com"}

        with django_capture_on_commit_callbacks(execute=True):
            duplicate = send_invitation(
                submission, email="invitee@example.com", sender=sender
            )
            upper = send_invitation(
                submission, email="INVITEE@example.com", sender=sender
            )

        assert duplicate.pk == invitation.pk
        assert upper.pk == invitation.pk
        assert len(djmail.outbox) == 1
        assert submission.invitations.count() == 1
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.send")
            .count()
            == 1
        )


def test_send_invitation_swallows_render_failure(monkeypatch):
    event = EventFactory()
    sender = UserFactory()
    submission = SubmissionFactory(event=event)

    def _raise(*_, **__):
        raise SendMailException("smtp dead")

    monkeypatch.setattr("pretalx.submission.domain.invitation.render_to_mail", _raise)

    with scope(event=event):
        invitation = send_invitation(
            submission, email="invitee@example.com", sender=sender
        )

        assert invitation.pk is not None
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.send")
            .exists()
        )


@pytest.mark.django_db(transaction=True)
def test_send_invitation_does_not_send_when_transaction_rolls_back():
    event = EventFactory()
    sender = UserFactory()
    submission = SubmissionFactory(event=event)
    djmail.outbox = []

    def invite_and_fail():
        with transaction.atomic():
            send_invitation(submission, email="invitee@example.com", sender=sender)
            raise RuntimeError("later step failed")

    with scope(event=event), pytest.raises(RuntimeError):
        invite_and_fail()

    with scope(event=event):
        assert djmail.outbox == []
        assert list(submission.invitations.all()) == []


_PHISH_LINK_RE = re.compile(r'<a[^>]*href="https://phish\.com[^"]*"')


def _phish_link_count(rendered):
    return len(_PHISH_LINK_RE.findall(rendered))


def test_send_invitation_blocks_injection_via_title_and_speaker_name(
    django_capture_on_commit_callbacks,
):
    event = EventFactory()
    submission = SubmissionFactory(event=event, title="[click](https://phish.com)")
    inviting_user = UserFactory(
        name="[Click here to secure your account](https://phish.com)"
    )
    djmail.outbox = []

    with scope(event=event), django_capture_on_commit_callbacks(execute=True):
        send_invitation(submission, email="victim@example.com", sender=inviting_user)
        invitation = submission.invitations.get(email="victim@example.com")

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert len(sent.alternatives) == 1
    html_body = sent.alternatives[0][0]
    assert _phish_link_count(html_body) == 0
    assert invitation.token in html_body


def test_retract_invitation_deletes_row_and_logs():
    submission = SubmissionFactory()
    user = UserFactory()
    invitation = SubmissionInvitationFactory(
        submission=submission, email="test@example.com"
    )

    retract_invitation(invitation, person=user)

    assert not SubmissionInvitation.objects.filter(pk=invitation.pk).exists()
    log = submission.logged_actions().get(
        action_type="pretalx.submission.invitation.retract"
    )
    assert log.person == user
    assert log.data == {"email": "test@example.com"}


def test_accept_invitation_adds_speaker_logs_and_deletes():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        invitation = SubmissionInvitationFactory(
            submission=submission, email="invitee@example.com"
        )
        invitation_pk = invitation.pk

        accept_invitation(invitation, user=user)

        assert submission.speakers.filter(user=user).exists()
        assert not submission.invitations.filter(pk=invitation_pk).exists()
        log = submission.logged_actions().get(
            action_type="pretalx.submission.invitation.accept"
        )
        assert log.data == {"email": "invitee@example.com"}
