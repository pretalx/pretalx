# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.mail.domain.queue import (
    copy_to_draft,
    create_mails_for_template,
    expire_stale_queued_mails,
    send_outbox_mails,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db]


def test_create_mails_for_template_skips_missing_user():
    event = EventFactory()
    template = MailTemplateFactory(event=event)

    with scope(event=event):
        result = create_mails_for_template(template, recipients=[{"user_id": 999999}])

    assert result["count"] == 0
    assert result["render_failures"] == 0


def test_create_mails_for_template_skip_queue_handles_send_failure(monkeypatch):
    event = EventFactory()
    template = MailTemplateFactory(event=event)
    speaker = SpeakerFactory(event=event)

    def broken_send(*args, **kwargs):
        raise RuntimeError("SMTP exploded")

    monkeypatch.setattr("pretalx.mail.domain.queue.send_queued_mail", broken_send)

    with scope(event=event):
        result = create_mails_for_template(
            template, recipients=[{"user_id": speaker.user.pk}], skip_queue=True
        )

    assert result["count"] == 1
    assert result["skip_queue"] is True


def test_send_outbox_mails_sends_draft_mails():
    event = EventFactory()
    user = UserFactory()
    mail_a = QueuedMailFactory(event=event, to=user.email)
    mail_b = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail_a.pk, mail_b.pk])

    assert result == {"count": 2}
    assert len(djmail.outbox) == 2


def test_send_outbox_mails_skips_non_draft():
    """Mails that are no longer DRAFT (e.g. already sent) are skipped."""
    event = EventFactory()
    user = UserFactory()
    draft_mail = QueuedMailFactory(event=event, to=user.email)
    sent_mail = QueuedMailFactory(
        event=event, to=user.email, state=QueuedMailStates.SENT
    )
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[draft_mail.pk, sent_mail.pk])

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1


def test_send_outbox_mails_with_requestor():
    event = EventFactory()
    user = UserFactory()
    requestor = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail.pk], requestor=requestor)

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1


def test_send_outbox_mails_empty_list():
    event = EventFactory()

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[])

    assert result == {"count": 0}


def test_send_outbox_mails_handles_send_failure(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)

    def broken_send(*args, **kwargs):
        raise RuntimeError("SMTP exploded")

    monkeypatch.setattr("pretalx.mail.domain.queue.send_queued_mail", broken_send)

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail.pk])

    assert result == {"count": 1}


def test_stale_sending_mail_marked_as_failed(event):
    """Mails stuck in SENDING state for over an hour are marked as failed
    with a timeout error."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=mail.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    count = expire_stale_queued_mails()

    assert count == 1
    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Timed out" in mail.error_data["error"]
    assert mail.error_data["type"] == "TimeoutError"


def test_recent_sending_mail_not_marked_as_failed(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    count = expire_stale_queued_mails()

    assert count == 0
    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENDING
    assert mail.has_error is False


def test_copy_to_draft_creates_new_draft(event):
    original = QueuedMailFactory(
        event=event,
        state=QueuedMailStates.SENT,
        subject="Original",
        text="Original text",
        to="recipient@example.com",
        error_data={"error": "stale"},
    )

    copy = copy_to_draft(original)

    assert copy.pk != original.pk
    assert copy.state == QueuedMailStates.DRAFT
    assert copy.sent is None
    assert copy.error_data is None
    assert copy.error_timestamp is None
    assert copy.subject == "Original"
    assert copy.text == "Original text"
    assert copy.to == "recipient@example.com"


def test_copy_to_draft_preserves_to_users(event):
    user = UserFactory()
    original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    original.to_users.add(user)

    copy = copy_to_draft(original)
    assert list(copy.to_users.all()) == [user]
