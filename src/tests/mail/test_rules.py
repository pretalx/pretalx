# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.rules import can_edit_mail
from tests.factories import QueuedMailFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (QueuedMailStates.DRAFT, True),
        (QueuedMailStates.SENDING, False),
        (QueuedMailStates.SENT, False),
    ),
)
def test_can_edit_mail_allows_only_drafts(state, expected):
    mail = QueuedMailFactory(state=state)
    assert can_edit_mail(None, mail) is expected


def test_can_edit_mail_rejects_objects_without_state():
    """Objects without a state attribute should not be editable."""
    assert can_edit_mail(None, object()) is False
