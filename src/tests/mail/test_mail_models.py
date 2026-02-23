# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

import datetime as dt
from smtplib import SMTPAuthenticationError
from unittest.mock import patch

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.mail import TolerantDict
from pretalx.mail.models import QueuedMail, QueuedMailStates
from pretalx.mail.tasks import mark_stale_sending_mails_as_failed


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("1", "a"),
        ("2", "b"),
        ("3", "3"),
    ),
)
def test_tolerant_dict(key, value):
    d = TolerantDict({"1": "a", "2": "b"})
    assert d[key] == value


@pytest.mark.django_db
def test_sent_mail_sending(sent_mail):
    assert str(sent_mail)
    with pytest.raises(Exception):  # noqa: B017, PT011
        sent_mail.send()


@pytest.mark.django_db
def test_mail_template_model(mail_template):
    assert mail_template.event.slug in str(mail_template)


@pytest.mark.parametrize("commit", (True, False))
@pytest.mark.django_db
def test_mail_template_model_to_mail(mail_template, commit):
    mail_template.to_mail("testdummy@exacmple.com", None, commit=commit)


@pytest.mark.django_db
def test_mail_template_model_to_mail_fails_without_address(mail_template):
    with pytest.raises(TypeError):
        mail_template.to_mail(1, None)


@pytest.mark.django_db
def test_mail_template_model_to_mail_shortens_subject(mail_template):
    mail_template.subject = "A" * 300
    mail = mail_template.to_mail("testdummy@exacmple.com", None, commit=False)
    assert len(mail.subject) == 199


@pytest.mark.django_db
def test_mail_submission_present_in_context(mail_template, submission, event):
    with scope(event=event):
        mail = mail_template.to_mail(
            "testdummy@exacmple.com",
            None,
            context_kwargs={"submission": submission},
        )
        mail.save()
        assert mail.submissions.all().contains(submission)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("text", "signature", "expected"),
    (
        ("test", None, "test"),
        ("test", "sig", "test\n-- \nsig"),
        ("test", "-- \nsig", "test\n-- \nsig"),
    ),
)
def test_mail_make_text(event, text, signature, expected):
    if signature:
        event.mail_settings["signature"] = signature
        event.save()
    assert QueuedMail(text=text, event=event).make_text() == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("text", "prefix", "expected"),
    (
        ("test", None, "test"),
        ("test", "pref", "[pref] test"),
        ("test", "[pref]", "[pref] test"),
    ),
)
def test_mail_prefixed_subject(event, text, prefix, expected):
    if prefix:
        event.mail_settings["subject_prefix"] = prefix
        event.save()
    assert QueuedMail(text=text, subject=text, event=event).prefixed_subject == expected


@pytest.mark.django_db
def test_mail_state_draft_to_sending_to_sent(mail):
    assert mail.state == QueuedMailStates.DRAFT
    mail.send()
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


@pytest.mark.django_db
def test_mark_mail_failed(mail):
    mail.state = QueuedMailStates.SENDING
    mail.save()
    mail.mark_failed(Exception("SMTP auth failed"))
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data == {"error": "SMTP auth failed", "type": "Exception"}
    assert mail.error_timestamp is not None
    assert mail.has_error


@pytest.mark.django_db
def test_mark_mail_sent(mail):
    mail.state = QueuedMailStates.SENDING
    mail.save()
    mail.mark_sent()
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert mail.error_data is None


@pytest.mark.django_db
def test_retry_failed_mail_clears_error(mail, event):
    with scope(event=event):
        mail.mark_failed(Exception("SMTP auth failed"))
        mail.refresh_from_db()
        assert mail.has_error
        mail.send()
        mail.refresh_from_db()
        assert mail.state == QueuedMailStates.SENT
        assert mail.error_data is None
        assert mail.error_timestamp is None


@pytest.mark.django_db
def test_has_error_property(mail):
    assert not mail.has_error
    mail.error_data = {"error": "test", "type": "Exception"}
    assert mail.has_error
    mail.state = QueuedMailStates.SENT
    assert not mail.has_error


@pytest.mark.django_db
def test_copy_to_draft_clears_error(mail, event):
    with scope(event=event):
        mail.state = QueuedMailStates.SENT
        mail.sent = mail.created
        mail.error_data = {"error": "test", "type": "Exception"}
        mail.save()
        new_mail = mail.copy_to_draft()
        assert new_mail.state == QueuedMailStates.DRAFT
        assert new_mail.sent is None
        assert new_mail.error_data is None
        assert new_mail.error_timestamp is None


@pytest.mark.django_db
def test_send_nonpersisted_mail_sets_sent(mail_template, event):
    mail = mail_template.to_mail("test@example.com", event, commit=False)
    assert mail.pk is None
    mail.send()
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


@pytest.mark.django_db
def test_apply_async_failure_marks_mail_failed(mail, event):
    with scope(event=event):
        with patch(
            "pretalx.common.mail.mail_send_task.apply_async",
            side_effect=Exception("Connection refused"),
        ):
            mail.send()
        mail.refresh_from_db()
        assert mail.state == QueuedMailStates.DRAFT
        assert mail.has_error
        assert "Connection refused" in mail.error_data["error"]


@pytest.mark.django_db
def test_smtp_auth_failure_marks_mail_failed(mail, event):
    with scope(event=event):
        with patch(
            "django.core.mail.backends.locmem.EmailBackend.send_messages",
            side_effect=SMTPAuthenticationError(
                535,
                b"5.7.8 Username and Password not accepted.",
            ),
        ):
            mail.send()
        mail.refresh_from_db()
        assert mail.state == QueuedMailStates.DRAFT
        assert mail.has_error
        assert "Username and Password not accepted" in mail.error_data["error"]
        assert mail.error_data["type"] == "SMTPAuthenticationError"
        assert mail.error_data["smtp_code"] == 535
        assert mail.sent is None


@pytest.mark.django_db
def test_stale_sending_mail_marked_as_failed(mail):
    mail.state = QueuedMailStates.SENDING
    mail.save()
    QueuedMail.objects.filter(pk=mail.pk).update(updated=now() - dt.timedelta(hours=2))
    mark_stale_sending_mails_as_failed(None)
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error
    assert "Timed out" in mail.error_data["error"]
    assert mail.error_data["type"] == "TimeoutError"


@pytest.mark.django_db
def test_recent_sending_mail_not_marked_as_failed(mail):
    mail.state = QueuedMailStates.SENDING
    mail.save()
    mark_stale_sending_mails_as_failed(None)
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENDING
    assert not mail.has_error
