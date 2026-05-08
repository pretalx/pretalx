# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.models.log import ActivityLog
from pretalx.mail.models import QueuedMail, QueuedMailStates
from pretalx.mail.signals import expire_stale_mails_periodic
from pretalx.mail.tasks import task_send_outbox_mails
from tests.factories import EventFactory, QueuedMailFactory, UserFactory

pytestmark = [pytest.mark.django_db]


def test_task_send_outbox_mails_dispatches_with_requestor():
    """The celery wrapper looks up the requestor by id and threads it through
    to mail.send so it lands on the activity log."""
    event = EventFactory()
    user = UserFactory()
    requestor = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    result = task_send_outbox_mails.apply(
        kwargs={
            "event_id": event.pk,
            "mail_pks": [mail.pk],
            "requestor_id": requestor.pk,
        }
    ).result

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        log = ActivityLog.objects.get(
            action_type="pretalx.mail.sent", object_id=mail.pk
        )
    assert log.person == requestor


def test_expire_stale_queued_mails_receiver_marks_and_logs(event, caplog):
    """The signals.py receiver delegates to the domain helper and emits a
    warning when anything was reset."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=mail.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    with caplog.at_level("WARNING", logger="pretalx.mail.signals"):
        expire_stale_mails_periodic(sender=None)

    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert "Expired 1 stale queued mails" in caplog.text
