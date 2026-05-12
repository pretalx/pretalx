# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.mail.domain.queries import outbox_mails, sent_mails
from pretalx.mail.enums import QueuedMailStates
from tests.factories import QueuedMailFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_outbox_mails_returns_drafts_only(event):
    draft = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    assert list(outbox_mails(event)) == [draft]


def test_outbox_mails_orders_newest_first(event):
    older = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    newer = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)

    assert list(outbox_mails(event)) == [newer, older]


def test_outbox_mails_annotates_computed_state(event):
    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.DRAFT, error_data={"error": "boom"}
    )

    result = list(outbox_mails(event))

    assert result == [mail]
    assert result[0].computed_state == "failed"


def test_sent_mails_returns_sent_and_sending(event):
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    sent = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sending = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    assert set(sent_mails(event)) == {sent, sending}
