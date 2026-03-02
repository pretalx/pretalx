# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.mail import MailTemplateTable, OutboxMailTable, SentMailTable
from tests.factories import EventFactory, QueuedMailFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


def test_mail_template_table_default_columns():
    assert MailTemplateTable.default_columns == ("role", "subject")


def test_outbox_mail_table_default_columns():
    assert OutboxMailTable.default_columns == (
        "subject",
        "to_recipients",
        "submissions",
        "template_info",
    )


@pytest.mark.django_db
def test_outbox_mail_table_set_columns_moves_status_display_first(event):
    mail = QueuedMailFactory(event=event)
    table = OutboxMailTable([mail], event=event, user=UserFactory.build())

    table._set_columns(["subject", "to_recipients", "status_display"])

    assert table.sequence[0] == "status_display"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale_value", "expected"),
    (("en", "English"), ("xx-unknown", "xx-unknown"), ("", ""), (None, "")),
)
def test_outbox_mail_table_render_locale(event, locale_value, expected):
    mail = QueuedMailFactory(event=event)
    table = OutboxMailTable([mail], event=event, user=UserFactory.build())

    assert table.render_locale(locale_value) == expected


def test_sent_mail_table_default_columns():
    assert SentMailTable.default_columns == (
        "sent",
        "subject",
        "to_recipients",
        "submissions",
        "template_info",
    )


def test_sent_mail_table_has_no_actions():
    assert SentMailTable.actions is None


def test_sent_mail_table_inherits_outbox_meta_model():
    assert SentMailTable.Meta.model == OutboxMailTable.Meta.model
