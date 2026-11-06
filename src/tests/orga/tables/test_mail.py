# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.mail import OutboxMailTable
from tests.factories import EventFactory, QueuedMailFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.django_db
def test_outbox_mail_table_set_columns_moves_state_first(event):
    mail = QueuedMailFactory(event=event)
    table = OutboxMailTable([mail], event=event, user=UserFactory.build())

    table._set_columns(["subject", "to_recipients", "state"])

    assert table.sequence[0] == "state"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale_value", "expected"),
    (("en", "English"), ("xx-unknown", "xx-unknown"), ("", ""), (None, "")),
)
def test_outbox_mail_table_render_locale(event, locale_value, expected):
    mail = QueuedMailFactory(event=event)
    table = OutboxMailTable([mail], event=event, user=UserFactory.build())

    assert table.render_locale(locale_value) == expected
