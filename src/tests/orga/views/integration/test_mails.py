# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from django.core import mail as djmail
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.models import (
    MailTemplate,
    MailTemplateRoles,
    QueuedMail,
    QueuedMailStates,
)
from pretalx.mail.signals import request_pre_send
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def mail_template(event):
    with scopes_disabled():
        return MailTemplateFactory(event=event, reply_to="orga@orga.org")


@pytest.fixture
def draft_mail(event, mail_template):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        return mail_template.to_mail(speaker.user, event)


@pytest.fixture
def second_draft_mail(event, mail_template):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        return mail_template.to_mail(speaker.user, event)


@pytest.fixture
def sent_mail(event, mail_template):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        mail = mail_template.to_mail(speaker.user, event)
        mail.send()
        mail.refresh_from_db()
    return mail


@pytest.fixture
def submission(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    return sub


@pytest.fixture
def other_submission(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    return sub


@pytest.mark.parametrize("item_count", (1, 3))
def test_outbox_list_view(
    client, event, mail_template, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        mails = []
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            mails.append(mail_template.to_mail(speaker.user, event))

    with django_assert_num_queries(27):
        response = client.get(event.orga_urls.outbox)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(m.subject in content for m in mails)


@pytest.mark.parametrize("item_count", (1, 3))
def test_sent_mail_list_view(
    client, event, mail_template, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        sent_mails = []
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            m = mail_template.to_mail(speaker.user, event)
            m.send()
            m.refresh_from_db()
            sent_mails.append(m)

    with django_assert_num_queries(23):
        response = client.get(event.orga_urls.sent_mails)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(m.subject in content for m in sent_mails)


def test_mail_detail_edit_updates_recipient(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []
    with scopes_disabled():
        log_count = draft_mail.logged_actions().count()

    response = client.post(
        draft_mail.urls.base,
        follow=True,
        data={
            "to": "testWIN@example.com",
            "bcc": draft_mail.bcc or "",
            "cc": draft_mail.cc or "",
            "reply_to": draft_mail.reply_to or "",
            "subject": draft_mail.subject,
            "text": draft_mail.text or "",
        },
    )

    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.to == "testwin@example.com"
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert draft_mail.logged_actions().count() == log_count + 1


def test_mail_detail_edit_unchanged_no_log(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        log_count = draft_mail.logged_actions().count()

    response = client.post(
        draft_mail.urls.base,
        follow=True,
        data={
            "to": draft_mail.to or "",
            "bcc": draft_mail.bcc or "",
            "cc": draft_mail.cc or "",
            "reply_to": draft_mail.reply_to or "",
            "subject": draft_mail.subject,
            "text": draft_mail.text or "",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert draft_mail.logged_actions().count() == log_count


def test_mail_detail_edit_and_send(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        draft_mail.urls.base,
        follow=True,
        data={
            "to": "winner@example.com",
            "bcc": "bcc1@example.com,bcc2@example.com",
            "cc": "",
            "reply_to": draft_mail.reply_to or "",
            "subject": draft_mail.subject,
            "text": "Updated body.",
            "form": "send",
        },
    )

    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.to == "winner@example.com"
    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.body == "Updated body."
    assert sent.to == ["winner@example.com"]
    assert sent.bcc == ["bcc1@example.com", "bcc2@example.com"]


def test_mail_detail_cannot_edit_sent_mail(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        sent_mail.urls.base,
        follow=True,
        data={
            "to": "hacker@evil.com",
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject": "HACKED",
            "text": "pwned",
        },
    )

    assert response.status_code == 200
    sent_mail.refresh_from_db()
    assert sent_mail.to != "hacker@evil.com"
    assert sent_mail.subject != "HACKED"


def test_send_single_mail(client, event, draft_mail, second_draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 2
        )

    response = client.post(draft_mail.urls.send, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )


def test_send_nonexistent_mail_shows_error(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse(
        "orga:mails.outbox.mail.send",
        kwargs={"event": event.slug, "pk": draft_mail.pk + 9999},
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )


def test_cannot_send_already_sent_mail(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    before = sent_mail.sent

    response = client.post(sent_mail.urls.send, follow=True)

    assert response.status_code == 200
    sent_mail.refresh_from_db()
    assert sent_mail.sent == before
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.SENT).count()
            == 1
        )


def test_send_all_mails(client, event, draft_mail, second_draft_mail, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 2
        )

    response = client.get(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 2
        )

    response = client.post(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )


def test_retry_all_failed_mails(client, event, draft_mail, second_draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        draft_mail.error_data = {"error": "SMTP auth failed", "type": "Exception"}
        draft_mail.save()

    response = client.post(event.orga_urls.send_outbox + "?failed_only=1", follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )
        second_draft_mail.refresh_from_db()
        assert second_draft_mail.state == QueuedMailStates.DRAFT


def test_delete_single_mail(client, event, draft_mail, second_draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 2

    response = client.post(draft_mail.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 1


def test_delete_all_by_template(
    client, event, draft_mail, second_draft_mail, sent_mail
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(draft_mail.urls.delete + "?all=true", follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )
        assert QueuedMail.objects.filter(event=event).count() == 1


def test_cannot_discard_sent_mail(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 1

    response = client.get(sent_mail.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 1


def test_purge_outbox(client, event, draft_mail, second_draft_mail, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 2
        )
        assert QueuedMail.objects.filter(event=event).count() == 3

    response = client.get(event.orga_urls.purge_outbox, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 2
        )

    response = client.post(event.orga_urls.purge_outbox, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )
        assert QueuedMail.objects.filter(event=event).count() == 1


def test_copy_sent_mail_to_draft(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 1

    response = client.post(sent_mail.urls.copy, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 2
        new_mail = QueuedMail.objects.filter(
            event=event, state=QueuedMailStates.DRAFT
        ).first()
        assert new_mail.subject == sent_mail.subject


def test_mail_preview(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse(
        "orga:mails.outbox.mail.preview",
        kwargs={"event": event.slug, "pk": draft_mail.pk},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert str(draft_mail.text) in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_template_list_view(
    client, event, mail_template, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        MailTemplateFactory.create_batch(item_count - 1, event=event)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.mail_templates, follow=True)

    assert response.status_code == 200
    assert str(mail_template.subject) in response.content.decode()


def test_create_template(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        before = MailTemplate.objects.filter(event=event).count()

    response = client.post(
        event.orga_urls.new_template,
        follow=True,
        data={"subject_0": "[test] subject", "text_0": "text"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before + 1
        assert MailTemplate.objects.get(event=event, subject__contains="[test] subject")


@pytest.mark.parametrize("variant", ("custom", "fixed", "update"))
def test_edit_template(client, event, mail_template, variant):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        if variant == "fixed":
            target = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)
        elif variant == "update":
            target = event.get_mail_template(MailTemplateRoles.NEW_SCHEDULE)
        else:
            target = mail_template
        log_count = target.logged_actions().count()

    response = client.post(
        target.urls.edit,
        follow=True,
        data={"subject_0": "COMPLETELY NEW SUBJECT", "text_0": str(target.text)},
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert log_count + 1 == target.logged_actions().count()
        assert MailTemplate.objects.get(
            event=event, subject__contains="COMPLETELY NEW SUBJECT"
        )


def test_edit_template_unchanged_no_log(client, event, mail_template):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        log_count = mail_template.logged_actions().count()

    response = client.post(
        mail_template.urls.edit,
        follow=True,
        data={
            "subject_0": str(mail_template.subject),
            "text_0": str(mail_template.text),
            "reply_to": mail_template.reply_to or "",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert mail_template.logged_actions().count() == log_count


def test_cannot_add_invalid_placeholder_to_template(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        template = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)

    response = client.post(
        template.urls.edit,
        follow=True,
        data={
            "subject_0": "HACKED",
            "text_0": str(template.text) + "{wrong_placeholder}",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        template.refresh_from_db()
    assert "HACKED" not in str(template.subject)
    assert "{wrong_placeholder}" not in str(template.text)


def test_delete_template(client, event, mail_template):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        before = MailTemplate.objects.filter(event=event).count()

    response = client.get(mail_template.urls.delete, follow=True)
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before

    response = client.post(mail_template.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before - 1


def test_compose_session_mail_by_state(client, event, submission, other_submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        other_submission.accept()

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "state": "submitted",
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "hey {name}",
            "text_0": "about {submission_title}",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(
            QueuedMail.objects.filter(
                event=event, state=QueuedMailStates.DRAFT
            ).exclude(template__role=MailTemplateRoles.SUBMISSION_ACCEPT)
        )
        assert len(mails) == 1
        speaker = submission.speakers.first()
        assert mails[0].subject == f"hey {speaker.user.name}"
        assert mails[0].text == f"about {submission.title}"


def test_compose_session_mail_selected_submissions(
    client, event, submission, other_submission
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "submissions": [other_submission.code],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT)
        )
        assert len(mails) == 1
        assert list(mails[0].to_users.all()) == [other_submission.speakers.first().user]


def test_compose_session_mail_state_plus_specific_submission(
    client, event, published_talk_slot, other_submission
):
    """When both state and submissions are specified, mails are sent to the
    union: all submissions matching the state AND the explicitly listed
    submission (even if it's in a different state)."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).delete()
        confirmed_sub = published_talk_slot.submission

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "state": "submitted",
            "submissions": confirmed_sub.code,
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo {name}",
            "text_0": "bar {submission_title}",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT)
        )
        assert len(mails) == 2
        mail_texts = {m.text for m in mails}
        assert f"bar {confirmed_sub.title}" in mail_texts
        assert f"bar {other_submission.title}" in mail_texts


def test_compose_session_mail_immediate_send(
    client, event, submission, other_submission
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        QueuedMail.objects.filter(event=event).delete()
    djmail.outbox = []

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "submissions": [submission.code, other_submission.code],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "hi {name}",
            "text_0": "talk: {submission_title}",
            "skip_queue": "on",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.SENT).count()
            == 2
        )
    assert len(djmail.outbox) == 2


def test_compose_session_mail_no_recipients_fails(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={"bcc": "", "cc": "", "reply_to": "", "subject_0": "foo", "text_0": "bar"},
    )

    assert response.status_code == 200
    assert "at least one filter" in response.content.decode()
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )


def test_compose_session_mail_preview_no_recipients(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "state": "rejected",
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
            "action": "preview",
        },
    )

    assert response.status_code == 200
    assert "no recipients" in response.content.decode()


def test_compose_session_mail_by_track(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        track = TrackFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        submission.speakers.add(speaker)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
            "track": [track.pk],
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )


def test_compose_session_mail_by_submission_type(client, event, submission):
    """The submission_type filter only appears when the event has multiple types."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        SubmissionTypeFactory(event=event)
        sub_type_pk = submission.submission_type.pk

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
            "submission_type": [sub_type_pk],
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )


def test_compose_session_mail_track_and_type_no_duplicates(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        SubmissionTypeFactory(event=event)
        track = TrackFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        submission.speakers.add(speaker)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
            "track": [track.pk],
            "submission_type": [submission.submission_type.pk],
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 1
        )


def test_compose_session_mail_to_specific_speakers(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        speaker = submission.speakers.first()

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "speakers": [speaker.pk],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(QueuedMail.objects.filter(event=event, sent__isnull=True))
        assert len(mails) == 1
        assert list(mails[0].to_users.all()) == [speaker.user]


def test_compose_session_mail_by_content_locale(client):
    event = EventFactory(content_locale_array="en,de")
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "content_locale": ["en"],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event, sent__isnull=True).count() == 1


def test_compose_session_mail_multiple_states_failing_placeholders(
    client, event, published_talk_slot
):
    """When composing for multiple states with a placeholder that fails for some
    submissions (e.g. {session_room} for a submission without a slot), only
    successfully rendered mails are created."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)
        QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).delete()

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "state": ["submitted", "confirmed"],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo {name}",
            "text_0": "bar {session_room}",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT)
        )
        assert len(mails) == 1
        assert mails[0].text == f"bar {published_talk_slot.room.name}"


def test_compose_session_mail_speakers_with_state_filter(
    client, event, submission, other_submission
):
    """When both 'state' and 'speakers' filters are specified, both sets
    of recipients receive mails (OR combination)."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        other_speaker = other_submission.speakers.first()
        QueuedMail.objects.filter(event=event, sent__isnull=True).delete()

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={
            "state": "submitted",
            "speakers": [other_speaker.pk],
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "foo",
            "text_0": "bar",
        },
    )

    assert response.status_code == 200
    with scopes_disabled():
        mails = list(QueuedMail.objects.filter(event=event, sent__isnull=True))
        recipients = set()
        for mail in mails:
            recipients.update(mail.to_users.all())
        assert submission.speakers.first().user in recipients
        assert other_speaker.user in recipients


def test_compose_session_mail_from_template(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        template = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)

    response = client.get(
        event.orga_urls.compose_mails_sessions + f"?template={template.pk}", follow=True
    )

    assert response.status_code == 200
    assert str(template.subject) in response.content.decode()


def test_compose_session_mail_from_wrong_template(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        template = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)

    response = client.get(
        event.orga_urls.compose_mails_sessions + f"?template={template.pk}000",
        follow=True,
    )

    assert response.status_code == 200
    assert str(template.subject) not in response.content.decode()


def test_compose_teams_mail_sends_directly(client, event):
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=True)
    client.force_login(user)
    with scopes_disabled():
        reviewer = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(reviewer)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.compose_mails_teams,
        follow=True,
        data={
            "recipients": str(team.pk),
            "subject_0": "hi {name}",
            "text_0": "hello {name}",
        },
    )

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == f"hi {reviewer.name}"
    assert djmail.outbox[0].body == f"hello {reviewer.name}"


def test_compose_teams_mail_multiple_teams(client, event):
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=True)
    client.force_login(user)
    with scopes_disabled():
        user1 = UserFactory()
        user2 = UserFactory()
        team1 = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team2 = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team1.members.add(user1)
        team2.members.add(user2)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.compose_mails_teams,
        follow=True,
        data={
            "recipients": [str(team1.pk), str(team2.pk)],
            "subject_0": "hi {name}",
            "text_0": "mail {email}",
        },
    )

    assert response.status_code == 200
    assert len(djmail.outbox) == 2
    for u in (user1, user2):
        sent = next(m for m in djmail.outbox if m.subject == f"hi {u.name}")
        assert sent.body == f"mail {u.email}"


def test_send_draft_reminders(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(speaker)
    djmail.outbox = []

    response = client.post(event.orga_urls.send_drafts_reminder, follow=True)

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    assert draft.title in djmail.outbox[0].body


def test_sending_status_no_ids_returns_286(client, event):
    """MailSendingStatus returns 286 when no valid PKs are provided."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:mails.sending_status", kwargs={"event": event.slug})
    response = client.get(url, {"ids": ""})

    assert response.status_code == 286


def test_sending_status_while_sending(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        draft_mail.state = QueuedMailStates.SENDING
        draft_mail.save()

    url = reverse("orga:mails.sending_status", kwargs={"event": event.slug})
    response = client.get(url, {"ids": str(draft_mail.pk)})

    assert response.status_code == 200
    assert f"mail-status-{draft_mail.pk}" in response.content.decode()
    assert "HX-Trigger" not in response.headers


def test_sending_status_stops_when_done(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:mails.sending_status", kwargs={"event": event.slug})
    response = client.get(url, {"ids": str(sent_mail.pk)})

    assert response.status_code == 286
    assert response.headers.get("HX-Trigger") == "updateSidebarCount"


def test_sidebar_count(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:mails.sidebar_count", kwargs={"event": event.slug})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "sidebar-notification" in content
    assert ">1<" in content


def test_outbox_shows_failed_count(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        draft_mail.error_data = {"error": "SMTP auth failed", "type": "Exception"}
        draft_mail.save()

    response = client.get(event.orga_urls.outbox)

    assert response.status_code == 200
    content = response.content.decode()
    assert "failed to send" in content
    assert "Retry all failed" in content
    assert "Show failed" in content


def test_outbox_status_filter(client, event, draft_mail, second_draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        draft_mail.error_data = {"error": "SMTP auth failed", "type": "Exception"}
        draft_mail.save()

    response = client.get(event.orga_urls.outbox + "?status=failed")
    assert response.status_code == 200
    assert draft_mail.subject in response.content.decode()

    response = client.get(event.orga_urls.outbox + "?status=draft")
    assert response.status_code == 200
    assert second_draft_mail.subject in response.content.decode()


def test_send_single_mail_htmx_response(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(draft_mail.urls.send, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "updateSidebarCount"
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.SENT


def test_send_single_mail_blocked_by_exception(
    client, event, draft_mail, register_signal_handler
):
    def block_send(signal, sender, **kwargs):
        raise SendMailException("Sending blocked")

    register_signal_handler(request_pre_send, block_send)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(draft_mail.urls.send, follow=True)

    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT


def test_bulk_send_blocked_by_exception(
    client, event, draft_mail, register_signal_handler
):
    def block_send(signal, sender, **kwargs):
        raise SendMailException("Sending blocked")

    register_signal_handler(request_pre_send, block_send)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(event.orga_urls.send_outbox, follow=True)

    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT


def test_delete_post_sent_mail_shows_error(client, event, sent_mail):
    """POSTing delete on a sent mail shows an error, mail remains."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(sent_mail.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 1


def test_mail_detail_send_blocked_by_exception(
    client, event, draft_mail, register_signal_handler
):
    def block_send(signal, sender, **kwargs):
        raise SendMailException("Blocked")

    register_signal_handler(request_pre_send, block_send)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        draft_mail.urls.base,
        follow=True,
        data={
            "to": "recipient@example.com",
            "bcc": draft_mail.bcc or "",
            "cc": draft_mail.cc or "",
            "reply_to": draft_mail.reply_to or "",
            "subject": draft_mail.subject,
            "text": draft_mail.text or "",
            "form": "send",
        },
    )

    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT
    assert "Blocked" in response.content.decode()


def test_mail_detail_sent_without_template_shows_copy_button(client, event, sent_mail):
    """A sent mail without a template shows a 'Copy to draft' button."""
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        sent_mail.template = None
        sent_mail.save()

    response = client.get(sent_mail.urls.base)

    assert response.status_code == 200
    assert "Copy to draft" in response.content.decode()


def test_compose_session_mail_preview(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        data={
            "state": "submitted",
            "bcc": "",
            "cc": "",
            "reply_to": "",
            "subject_0": "Preview {name}",
            "text_0": "Hello {submission_title}",
            "action": "preview",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Subject:" in content
    with scopes_disabled():
        assert (
            QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).count()
            == 0
        )


def test_compose_teams_mail_blocked_by_exception(
    client, event, register_signal_handler
):
    def block_send(signal, sender, **kwargs):
        raise SendMailException("Blocked")

    register_signal_handler(request_pre_send, block_send)
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=True)
    client.force_login(user)

    response = client.get(event.orga_urls.compose_mails_teams)

    assert response.status_code == 302
    assert response.url == event.orga_urls.outbox


def test_bulk_send_empty_outbox(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(event.orga_urls.send_outbox, follow=True)

    assert response.status_code == 200
    assert "No emails to send" in response.content.decode()


@pytest.mark.parametrize(
    ("url_attr", "expected_title"),
    (("send_outbox", "Sending emails"), ("compose_mails_sessions", "Composing emails")),
)
def test_async_progress_page(
    client, event, settings, monkeypatch, url_attr, expected_title
):
    """Celery runs in eager mode with a DisabledBackend during tests, so the
    progress page is never reached.  We patch the Celery setting and the
    result lookup to return a PENDING result for a fake task ID."""
    settings.CELERY_TASK_ALWAYS_EAGER = False
    pending = SimpleNamespace(
        ready=lambda: False, state="PENDING", info=None, id="fake-id"
    )
    monkeypatch.setattr(
        "pretalx.common.views.mixins._get_celery_async_result", lambda _: pending
    )
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = getattr(event.orga_urls, url_attr) + "?async_id=fake-id"
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert expected_title in content
    assert event.orga_urls.outbox in content


def test_compose_teams_mail_preview(client, event):
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=True)
    client.force_login(user)
    with scopes_disabled():
        reviewer = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(reviewer)

    response = client.post(
        event.orga_urls.compose_mails_teams,
        data={
            "recipients": str(team.pk),
            "subject_0": "hi {name}",
            "text_0": "hello {name}",
            "action": "preview",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Subject:" in content
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event).count() == 0
