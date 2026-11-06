# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from i18nfield.strings import LazyI18nString

from pretalx.mail.enums import MailTemplateRoles
from pretalx.orga.tables.mail import MailTemplateTable, OutboxMailTable, SentMailTable
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

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


@pytest.mark.django_db
def test_outbox_table_value_hooks(event):
    speaker = SpeakerFactory(event=event, name="Ada")
    submission = SubmissionFactory(event=event, title="Talk")
    template = event.mail_templates.get(role=MailTemplateRoles.NEW_SUBMISSION)
    mail = QueuedMailFactory(
        event=event,
        to="x@example.org, y@example.org",
        cc="c@example.org,,d@example.org ",
        bcc="b@example.org",
        reply_to="r@example.org",
        template=template,
        locale="de",
        text="Body",
        error_data={"error": "boom"},
    )
    mail.to_speakers.add(speaker)
    mail.submissions.add(submission)
    plain = QueuedMailFactory(event=event, to=None, cc=None, bcc="", reply_to=None)
    email = speaker.effective_email
    user = UserFactory.build()
    plain, mail = OutboxMailTable.base_queryset(event, user)
    table = OutboxMailTable([mail, plain], event=event, user=user)

    assert table.value_to_recipients(mail) == ["Ada", "x@example.org, y@example.org"]
    assert table.value_to_recipients(plain) == []
    assert table.value_to_addresses(mail) == [email, "x@example.org", "y@example.org"]
    assert table.value_to_addresses(plain) == []
    assert table.value_cc(mail) == ["c@example.org", "d@example.org"]
    assert table.value_bcc(mail) == ["b@example.org"]
    assert table.value_reply_to(mail) == ["r@example.org"]
    assert table.value_cc(plain) == table.value_bcc(plain) == []
    assert table.value_reply_to(plain) == []
    assert table.base_columns["to_addresses"].export_only
    assert SentMailTable.base_columns["to_addresses"].export_only
    assert table.value_submissions(mail) == ["Talk"]
    assert table.value_template_role(mail) == template.role
    assert table.value_template_role(plain) is None
    table.configure_export(["state", "has_error", "locale", "text"])
    assert list(table.as_values())[1:] == [
        [mail.pk, "draft", True, "de", "Body"],
        [plain.pk, "draft", False, plain.locale, plain.text],
    ]


@pytest.mark.django_db
def test_mail_template_table_value_role(event):
    custom = MailTemplateFactory(event=event, role=None)
    role = event.mail_templates.get(role=MailTemplateRoles.NEW_SUBMISSION)
    table = MailTemplateTable([custom, role], event=event, user=UserFactory.build())

    assert table.value_role(role) == role.role
    assert table.value_role(custom) is None
    custom.refresh_from_db()
    export_table = MailTemplateTable([custom], event=event, user=UserFactory.build())
    export_table.configure_export(["text"])
    text = list(export_table.as_values())[1][1]
    assert isinstance(text, LazyI18nString)
    assert text.data == custom.text.data
