# SPDX-FileCopyrightText: 2020-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django.test import override_settings

from pretalx.common.mail import mail_send_task


@pytest.mark.django_db
def test_mail_send(event):
    djmail.outbox = []
    mail_send_task("m@example.com", "S", "B", None, [], event.pk)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["m@example.com"]
    assert djmail.outbox[0].from_email == f"{event.name} <orga@orga.org>"
    assert djmail.outbox[0].reply_to == [f"{event.name} <{event.email}>"]


@pytest.mark.django_db
def test_mail_send_ignored_sender_but_custom_reply_to(event):
    event.mail_settings["reply_to"] = "sender@example.com"
    event.mail_settings["mail_from"] = "sender@example.com"
    event.save()
    djmail.outbox = []
    mail_send_task("m@example.com", "S", "B", None, [], event.pk)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["m@example.com"]
    assert djmail.outbox[0].from_email == f"{event.name} <orga@orga.org>"
    assert djmail.outbox[0].reply_to == [f"{event.name} <sender@example.com>"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "subject",
    [
        "Talk about\x0bthings",
        "Talk about\nthings",
        "Talk about\r\nthings",
        "Talk about\x00things",
        "Talk about\x7fthings",
    ],
)
def test_mail_send_strips_control_chars_from_subject(event, subject):
    djmail.outbox = []
    mail_send_task("m@example.com", subject, "B", None, [], event.pk)
    assert len(djmail.outbox) == 1
    assert "\x0b" not in djmail.outbox[0].subject
    assert "\n" not in djmail.outbox[0].subject
    assert "\r" not in djmail.outbox[0].subject
    assert "Talk about" in djmail.outbox[0].subject
    assert "things" in djmail.outbox[0].subject


@pytest.mark.django_db
def test_mail_send_exits_early_without_address(event):
    djmail.outbox = []
    mail_send_task("", "S", "B", None, [], event.pk)
    assert djmail.outbox == []


@pytest.mark.django_db
@override_settings(MAIL_FROM="Custom Sender <orga@orga.org>")
def test_mail_send_event_uses_event_name_as_sender(event):
    djmail.outbox = []
    mail_send_task("m@example.com", "S", "B", None, [], event.pk)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].from_email == f"{event.name} <orga@orga.org>"


@pytest.mark.django_db
def test_mail_send_respects_display_name_in_reply_to(event):
    event.mail_settings["reply_to"] = "Custom Reply <reply@example.com>"
    event.save()
    djmail.outbox = []
    mail_send_task("m@example.com", "S", "B", None, [], event.pk)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].reply_to == ["Custom Reply <reply@example.com>"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mail_from,expected_from",
    [
        ("Custom Sender <orga@orga.org>", "Custom Sender <orga@orga.org>"),
        ("orga@orga.org", "pretalx <orga@orga.org>"),
    ],
)
def test_mail_send_without_event(mail_from, expected_from):
    with override_settings(MAIL_FROM=mail_from):
        djmail.outbox = []
        mail_send_task("m@example.com", "S", "B", None)
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].from_email == expected_from
