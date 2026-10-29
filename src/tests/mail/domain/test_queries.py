# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.mail.domain.queries import outbox_mails, sent_mails
from pretalx.mail.enums import QueuedMailStates
from tests.factories import QueuedMailFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_outbox_and_sent_mails_split_by_state_newest_first(event):
    older = QueuedMailFactory(
        event=event, state=QueuedMailStates.DRAFT, error_data={"error": "boom"}
    )
    newer = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    sent = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sending = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    outbox = list(outbox_mails(event))

    assert outbox == [newer, older]
    assert [mail.computed_state for mail in outbox] == ["draft", "failed"]
    assert set(sent_mails(event)) == {sent, sending}
