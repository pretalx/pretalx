# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from django.core import mail as djmail
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.queue import save_draft
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_draft
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.mail.models import MailTemplate, QueuedMail
from pretalx.mail.signals import request_pre_send
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
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


def _draft_mail(event, mail_template):
    speaker = SpeakerFactory(event=event)
    mail = render_template_to_mail(mail_template, locale=speaker.user.locale)
    save_draft(mail, to_speakers=[speaker])
    return mail


@pytest.fixture
def draft_mail(event, mail_template):
    with scopes_disabled():
        return _draft_mail(event, mail_template)


@pytest.fixture
def second_draft_mail(event, mail_template):
    with scopes_disabled():
        return _draft_mail(event, mail_template)


@pytest.fixture
def sent_mail(event, mail_template):
    with scopes_disabled():
        mail = _draft_mail(event, mail_template)
        send_draft(mail)
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


EVENT_MAIL_URLS = (
    "outbox",
    "sent_mails",
    "send_outbox",
    "purge_outbox",
    "compose_mails",
    "compose_mails_sessions",
    "send_drafts_reminder",
    "mail_templates",
    "preview",
    "sending_status",
    "sidebar_count",
)

COMPOSE_DATA = {
    "bcc": "",
    "cc": "",
    "reply_to": "",
    "subject_0": "foo",
    "text_0": "bar",
}


def _event_mail_url(event, mail, url_attr):
    if url_attr == "preview":
        return reverse(
            "orga:mails.outbox.mail.preview",
            kwargs={"event": event.slug, "pk": mail.pk},
        )
    if url_attr == "sending_status":
        url = reverse("orga:mails.sending_status", kwargs={"event": event.slug})
        return f"{url}?ids={mail.pk}"
    if url_attr == "sidebar_count":
        return reverse("orga:mails.sidebar_count", kwargs={"event": event.slug})
    return getattr(event.orga_urls, url_attr)


def _drafts(event):
    with scopes_disabled():
        return QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT)


def _mail_count(event, **filters):
    with scopes_disabled():
        return QueuedMail.objects.filter(event=event, **filters).count()


def _delete_drafts(event):
    with scopes_disabled():
        QueuedMail.objects.filter(event=event, state=QueuedMailStates.DRAFT).delete()


def test_mail_views_redirect_anonymous_users_to_login(client, event, draft_mail):
    for url_attr in EVENT_MAIL_URLS:
        response = client.get(_event_mail_url(event, draft_mail, url_attr))

        assert response.status_code == 302, url_attr
        assert "/login/" in response.url


def test_mail_views_hidden_from_users_without_mail_permission(
    client, event, draft_mail
):
    for user in (UserFactory(), make_orga_user(event, can_change_submissions=False)):
        client.force_login(user)
        for url_attr in EVENT_MAIL_URLS:
            response = client.get(_event_mail_url(event, draft_mail, url_attr))

            assert response.status_code == 404, url_attr
            assert str(draft_mail.subject) not in response.content.decode()

    for url_attr in ("base", "send", "delete", "copy"):
        response = client.post(getattr(draft_mail.urls, url_attr))

        assert response.status_code == 404, url_attr
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT
    assert _mail_count(event) == 1


def test_compose_teams_mail_requires_team_permission(client, event):
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=False)
    client.force_login(user)

    response = client.get(event.orga_urls.compose_mails_teams)

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_outbox_list_view(
    client, event, mail_template, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        mails = [_draft_mail(event, mail_template) for _ in range(item_count)]

    with django_assert_num_queries(19):
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
            m = _draft_mail(event, mail_template)
            send_draft(m)
            m.refresh_from_db()
            sent_mails.append(m)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.sent_mails)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(m.subject in content for m in sent_mails)


def test_mail_detail_edit_and_send(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []
    with scopes_disabled():
        log_count = draft_mail.logged_actions().count()
    data = {
        "to": draft_mail.to or "",
        "bcc": draft_mail.bcc or "",
        "cc": draft_mail.cc or "",
        "reply_to": draft_mail.reply_to or "",
        "subject": draft_mail.subject,
        "text": draft_mail.text or "",
    }

    response = client.get(_event_mail_url(event, draft_mail, "preview"))
    assert response.status_code == 200
    assert str(draft_mail.text) in response.content.decode()

    response = client.post(draft_mail.urls.base, follow=True, data=data)
    assert response.status_code == 200
    with scopes_disabled():
        assert draft_mail.logged_actions().count() == log_count

    response = client.post(
        draft_mail.urls.base, follow=True, data={**data, "to": "testWIN@example.com"}
    )
    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.to == "testwin@example.com"
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert draft_mail.logged_actions().count() == log_count + 1

    response = client.post(
        draft_mail.urls.base,
        follow=True,
        data={
            **data,
            "to": "winner@example.com",
            "bcc": "bcc1@example.com,bcc2@example.com",
            "text": "Updated body.",
            "form": "send",
        },
    )
    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.to == "winner@example.com"
    assert draft_mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.body == "Updated body."
    assert sent.to == ["winner@example.com"]
    assert sent.bcc == ["bcc1@example.com", "bcc2@example.com"]


def test_sent_mail_is_immutable_and_copyable(client, event, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    before = sent_mail.sent

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

    response = client.post(sent_mail.urls.send, follow=True)
    assert response.status_code == 200
    sent_mail.refresh_from_db()
    assert sent_mail.sent == before
    assert _mail_count(event, state=QueuedMailStates.SENT) == 1

    response = client.get(sent_mail.urls.delete, follow=True)
    assert response.status_code == 200
    response = client.post(sent_mail.urls.delete, follow=True)
    assert response.status_code == 200
    assert _mail_count(event) == 1

    with scopes_disabled():
        sent_mail.template = None
        sent_mail.save()
    response = client.get(sent_mail.urls.base)
    assert response.status_code == 200
    assert "Copy to draft" in response.content.decode()

    response = client.post(sent_mail.urls.copy, follow=True)
    assert response.status_code == 200
    assert _mail_count(event) == 2
    with scopes_disabled():
        new_mail = _drafts(event).get()
        assert new_mail.subject == sent_mail.subject


def test_send_single_mail(client, event, draft_mail, second_draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    assert _drafts(event).count() == 2

    url = reverse(
        "orga:mails.outbox.mail.send",
        kwargs={"event": event.slug, "pk": draft_mail.pk + 9999},
    )
    response = client.post(url, follow=True)
    assert response.status_code == 200
    assert _drafts(event).count() == 2

    response = client.post(draft_mail.urls.send, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "updateSidebarCount"
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.SENT
    assert list(_drafts(event)) == [second_draft_mail]

    response = client.post(second_draft_mail.urls.send, follow=True)
    assert response.status_code == 200
    assert "The email has been sent." in response.content.decode()
    assert _drafts(event).count() == 0


def test_send_all_mails(client, event, draft_mail, second_draft_mail, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        draft_mail.error_data = {"error": "SMTP auth failed", "type": "Exception"}
        draft_mail.save()

    response = client.post(event.orga_urls.send_outbox + "?failed_only=1", follow=True)
    assert response.status_code == 200
    assert list(_drafts(event)) == [second_draft_mail]

    response = client.get(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    assert list(_drafts(event)) == [second_draft_mail]

    response = client.post(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    assert _drafts(event).count() == 0
    assert _mail_count(event, state=QueuedMailStates.SENT) == 3

    response = client.post(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    assert "No emails to send" in response.content.decode()


@pytest.mark.parametrize(
    ("mail_fixture", "next_url", "extra_params", "follows_next", "remaining_drafts"),
    (
        (
            "draft_mail",
            "/orga/event/{slug}/mails/outbox/?page_size=5&page=2",
            {},
            True,
            1,
        ),
        (
            "sent_mail",
            "/orga/event/{slug}/mails/outbox/?page_size=5&page=2",
            {},
            True,
            1,
        ),
        ("draft_mail", "https://evil.example.com/", {}, False, 1),
        (
            "draft_mail",
            "/orga/event/{slug}/mails/outbox/?page_size=5&page=2",
            {"all": "true"},
            True,
            0,
        ),
    ),
    ids=("deleted", "not_deletable", "rejects_external_url", "all_by_template"),
)
def test_delete_mail(
    client,
    event,
    request,
    second_draft_mail,
    mail_fixture,
    next_url,
    extra_params,
    follows_next,
    remaining_drafts,
):
    mail = request.getfixturevalue(mail_fixture)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    next_url = next_url.format(slug=event.slug)

    response = client.post(
        mail.urls.delete, query_params={"next": next_url, **extra_params}
    )

    assert response.status_code == 302
    assert response.url == (next_url if follows_next else str(event.orga_urls.outbox))
    assert _drafts(event).count() == remaining_drafts
    with scopes_disabled():
        assert QueuedMail.objects.filter(pk=mail.pk).exists() is (
            mail_fixture == "sent_mail"
        )


def test_purge_outbox(client, event, draft_mail, second_draft_mail, sent_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    assert _drafts(event).count() == 2
    assert _mail_count(event) == 3

    response = client.get(event.orga_urls.purge_outbox, follow=True)
    assert response.status_code == 200
    assert _drafts(event).count() == 2

    response = client.post(event.orga_urls.purge_outbox, follow=True)
    assert response.status_code == 200
    assert _drafts(event).count() == 0
    with scopes_disabled():
        assert list(QueuedMail.objects.filter(event=event)) == [sent_mail]


def test_copy_sent_mail_without_reachable_recipients_shows_error(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        mail = QueuedMail.objects.create(
            event=event, subject="Hi", text="Body", state=QueuedMailStates.SENT
        )
        mail.to_speakers.add(managed)

    response = client.post(mail.urls.copy, follow=True)

    assert response.status_code == 200
    assert _mail_count(event) == 1
    assert "could not be copied" in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_template_list_view(
    client, event, mail_template, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        MailTemplateFactory.create_batch(item_count - 1, event=event)

    with django_assert_num_queries(14):
        response = client.get(event.orga_urls.mail_templates, follow=True)

    assert response.status_code == 200
    assert str(mail_template.subject) in response.content.decode()


def test_template_form_pages_name_the_template(client, event, mail_template):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        role_template = mail_template_by_role(event, MailTemplateRoles.NEW_SUBMISSION)
        role_heading = f"Email template: {role_template.get_role_display()}"

    for url, expected in (
        (mail_template.urls.edit, f"Email template: {mail_template.subject}"),
        (role_template.urls.edit, role_heading),
        (event.orga_urls.new_template, "New email template"),
    ):
        response = client.get(url)

        assert response.status_code == 200
        assert expected in response.content.decode()


def test_template_create_edit_and_delete(client, event, mail_template):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        before = MailTemplate.objects.filter(event=event).count()
        fixed_template = mail_template_by_role(event, MailTemplateRoles.NEW_SUBMISSION)
        update_template = mail_template_by_role(event, MailTemplateRoles.NEW_SCHEDULE)
        fixed_text = str(fixed_template.text)

    response = client.post(
        event.orga_urls.new_template,
        follow=True,
        data={"subject_0": "[test] subject", "text_0": "text"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before + 1
        assert MailTemplate.objects.get(event=event, subject__contains="[test] subject")

    for index, target in enumerate((mail_template, fixed_template, update_template)):
        with scopes_disabled():
            log_count = target.logged_actions().count()
            text = str(target.text)
        response = client.post(
            target.urls.edit,
            follow=True,
            data={"subject_0": f"COMPLETELY NEW SUBJECT {index}", "text_0": text},
        )
        assert response.status_code == 200
        with scopes_disabled():
            assert target.logged_actions().count() == log_count + 1
            assert MailTemplate.objects.get(
                event=event, subject__contains=f"COMPLETELY NEW SUBJECT {index}"
            )

    with scopes_disabled():
        mail_template.refresh_from_db(fields=["subject", "text", "reply_to"])
        log_count = mail_template.logged_actions().count()
    response = client.post(
        mail_template.urls.edit,
        follow=True,
        data={
            "subject_0": "COMPLETELY NEW SUBJECT 0",
            "text_0": str(mail_template.text),
            "reply_to": mail_template.reply_to or "",
        },
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert mail_template.logged_actions().count() == log_count

    response = client.post(
        fixed_template.urls.edit,
        follow=True,
        data={"subject_0": "HACKED", "text_0": fixed_text + "{wrong_placeholder}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        fixed_template.refresh_from_db(fields=["subject", "text"])
    assert str(fixed_template.subject) == "COMPLETELY NEW SUBJECT 1"
    assert str(fixed_template.text) == fixed_text

    response = client.get(mail_template.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before + 1

    response = client.post(mail_template.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert MailTemplate.objects.filter(event=event).count() == before
        assert not MailTemplate.objects.filter(pk=mail_template.pk).exists()


def test_compose_session_mail_validation(client, event, submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []
    with scopes_disabled():
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SUBMISSION)

    response = client.post(
        event.orga_urls.compose_mails_sessions, follow=True, data=COMPOSE_DATA
    )
    assert response.status_code == 200
    assert "at least one filter" in response.content.decode()

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={**COMPOSE_DATA, "submissions": [submission.code], "subject_0": ""},
    )
    assert response.status_code == 200
    soup = BeautifulSoup(response.content.decode(), "lxml")
    error_selector = '[aria-invalid="true"], .invalid-feedback'
    content = soup.find("legend", string="Content").find_parent("fieldset")
    recipients = soup.find("legend", string="Recipients").find_parent("fieldset")
    assert content.select(error_selector)
    assert recipients.select(error_selector) == []

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=rejected",
        follow=True,
        data={**COMPOSE_DATA, "skip_queue": "on"},
    )
    assert response.status_code == 200
    assert "no recipients" in response.content.decode()
    assert "about to immediately send" not in response.content.decode()

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=rejected",
        follow=True,
        data={**COMPOSE_DATA, "action": "preview"},
    )
    assert response.status_code == 200
    assert "no recipients" in response.content.decode()

    response = client.get(
        event.orga_urls.compose_mails_sessions + f"?template={template.pk}", follow=True
    )
    assert response.status_code == 200
    assert str(template.subject) in response.content.decode()

    response = client.get(
        event.orga_urls.compose_mails_sessions + f"?template={template.pk}000",
        follow=True,
    )
    assert response.status_code == 200
    assert str(template.subject) not in response.content.decode()

    assert _mail_count(event) == 0
    assert len(djmail.outbox) == 0


def test_compose_session_mail_recipients(client, event, submission, other_submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []
    with scopes_disabled():
        Submission.objects.filter(pk=other_submission.pk).update(
            state=SubmissionStates.ACCEPTED
        )
        speaker = submission.speakers.select_related("user", "event").first()
        other_speaker = other_submission.speakers.select_related(
            "user", "event"
        ).first()

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=submitted",
        follow=True,
        data={
            **COMPOSE_DATA,
            "subject_0": "hey {name}",
            "text_0": "about {submission_title}",
        },
    )
    assert response.status_code == 200
    with scopes_disabled():
        mail = _drafts(event).get()
        assert mail.subject == f"hey {speaker.user.name}"
        assert mail.text == f"about {submission.title}"
        assert list(mail.to_speakers.all()) == [speaker]
    _delete_drafts(event)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={**COMPOSE_DATA, "submissions": [other_submission.code]},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert list(_drafts(event).get().to_speakers.all()) == [other_speaker]
    _delete_drafts(event)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={**COMPOSE_DATA, "speakers": [speaker.pk]},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert list(_drafts(event).get().to_speakers.all()) == [speaker]
    _delete_drafts(event)

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=submitted",
        follow=True,
        data={**COMPOSE_DATA, "speakers": [other_speaker.pk]},
    )
    assert response.status_code == 200
    with scopes_disabled():
        recipients = {
            recipient for mail in _drafts(event) for recipient in mail.to_speakers.all()
        }
    assert recipients == {speaker, other_speaker}
    _delete_drafts(event)

    data = {
        **COMPOSE_DATA,
        "submissions": [submission.code, other_submission.code],
        "subject_0": "hi {name}",
        "text_0": "talk: {submission_title}",
        "skip_queue": "on",
    }
    # Submitting with skip_queue but without confirmation does not send: it
    # shows a confirmation that states the number of emails again.
    response = client.post(
        event.orga_urls.compose_mails_sessions, follow=True, data=data
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "about to immediately send 2 emails" in content
    assert "Send 2 emails now" in content
    assert _mail_count(event) == 0
    assert len(djmail.outbox) == 0

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        follow=True,
        data={**data, "action": "send_immediately"},
    )
    assert response.status_code == 200
    assert _drafts(event).count() == 0
    assert _mail_count(event, state=QueuedMailStates.SENT) == 2
    assert len(djmail.outbox) == 2


def test_compose_session_mail_by_track_and_type(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        SubmissionTypeFactory(event=event)
        track = TrackFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        submission.speakers.add(speaker)
        sub_type_pk = submission.submission_type.pk

    for query in (
        f"?track={track.pk}",
        f"?submission_type={sub_type_pk}",
        f"?track={track.pk}&submission_type={sub_type_pk}",
    ):
        response = client.post(
            f"{event.orga_urls.compose_mails_sessions}{query}",
            follow=True,
            data=COMPOSE_DATA,
        )

        assert response.status_code == 200
        with scopes_disabled():
            assert list(_drafts(event).get().to_speakers.all()) == [speaker]
        _delete_drafts(event)


def test_compose_session_mail_by_content_locale(client):
    event = EventFactory(content_locales=["en", "de"])
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?content_locale=en",
        follow=True,
        data=COMPOSE_DATA,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.filter(event=event, sent__isnull=True).count() == 1


def test_compose_session_mail_with_state_and_specific_submissions(
    client, event, published_talk_slot, other_submission
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        confirmed_sub = published_talk_slot.submission
        room_name = published_talk_slot.room.name
    _delete_drafts(event)

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=submitted",
        follow=True,
        data={
            **COMPOSE_DATA,
            "submissions": confirmed_sub.code,
            "subject_0": "foo {name}",
            "text_0": "bar {submission_title}",
        },
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert sorted(mail.text for mail in _drafts(event)) == sorted(
            [f"bar {confirmed_sub.title}", f"bar {other_submission.title}"]
        )
    _delete_drafts(event)

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=submitted&state=confirmed",
        follow=True,
        data={
            **COMPOSE_DATA,
            "subject_0": "foo {name}",
            "text_0": "bar {session_room}",
        },
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert [mail.text for mail in _drafts(event)] == [f"bar {room_name}"]


def test_compose_teams_mail(client, event):
    user = make_orga_user(event, can_change_submissions=True, can_change_teams=True)
    client.force_login(user)
    with scopes_disabled():
        reviewer = UserFactory()
        other_user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        other_team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(reviewer)
        other_team.members.add(other_user)
    djmail.outbox = []

    response = client.get(event.orga_urls.compose_mails_teams)
    assert response.status_code == 200

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
    assert "Subject:" in response.content.decode()
    assert _mail_count(event) == 0
    assert len(djmail.outbox) == 0

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

    djmail.outbox = []
    response = client.post(
        event.orga_urls.compose_mails_teams,
        follow=True,
        data={
            "recipients": [str(team.pk), str(other_team.pk)],
            "subject_0": "hi {name}",
            "text_0": "mail {email}",
        },
    )
    assert response.status_code == 200
    assert len(djmail.outbox) == 2
    for u in (reviewer, other_user):
        sent = next(m for m in djmail.outbox if m.subject == f"hi {u.name}")
        assert sent.body == f"mail {u.email}"


def test_send_draft_reminders(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(speaker)
        template = mail_template_by_role(event, MailTemplateRoles.DRAFT_REMINDER)
    djmail.outbox = []

    response = client.get(event.orga_urls.send_drafts_reminder)

    assert response.status_code == 200
    assert f'href="{template.urls.base}"' in response.content.decode()

    response = client.post(event.orga_urls.send_drafts_reminder, follow=True)

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    assert draft.title in djmail.outbox[0].body


def test_sending_status_and_sidebar_count(client, event, draft_mail):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    status_url = reverse("orga:mails.sending_status", kwargs={"event": event.slug})

    response = client.get(
        reverse("orga:mails.sidebar_count", kwargs={"event": event.slug})
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "sidebar-notification" in content
    assert ">1<" in content

    response = client.get(status_url, {"ids": ""})
    assert response.status_code == 286

    with scopes_disabled():
        draft_mail.state = QueuedMailStates.SENDING
        draft_mail.save()
    response = client.get(status_url, {"ids": str(draft_mail.pk)})
    assert response.status_code == 200
    assert f"mail-status-{draft_mail.pk}" in response.content.decode()
    assert "HX-Trigger" not in response.headers

    with scopes_disabled():
        draft_mail.state = QueuedMailStates.DRAFT
        draft_mail.save()
        send_draft(draft_mail)
    response = client.get(status_url, {"ids": str(draft_mail.pk)})
    assert response.status_code == 286
    assert response.headers.get("HX-Trigger") == "updateSidebarCount"


def test_outbox_failed_count_search_and_status_filter(
    client, event, draft_mail, second_draft_mail
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        speaker = draft_mail.to_speakers.select_related("user", "event").first()
        speaker.name = "Findable Speaker"
        speaker.save()
        # Both fixtures render the same template, so they need telling apart.
        draft_mail.subject = "Delivery failed here"
        draft_mail.error_data = {"error": "SMTP auth failed", "type": "Exception"}
        draft_mail.save()
        second_draft_mail.subject = "Still pending here"
        second_draft_mail.save()

    response = client.get(event.orga_urls.outbox)
    assert response.status_code == 200
    content = response.content.decode()
    assert "failed to send" in content
    assert "Retry all failed" in content
    assert "Show failed" in content
    assert "Delivery failed here" in content
    assert "Still pending here" in content

    response = client.get(event.orga_urls.outbox + "?q=Findable")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Delivery failed here" in content
    assert "Still pending here" not in content

    response = client.get(event.orga_urls.outbox + "?status=failed")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Delivery failed here" in content
    assert "Still pending here" not in content

    response = client.get(event.orga_urls.outbox + "?status=draft")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Still pending here" in content
    assert "Delivery failed here" not in content


def test_send_blocked_by_exception(client, event, draft_mail, register_signal_handler):
    def block_send(signal, sender, **kwargs):
        raise SendMailException("Blocked")

    register_signal_handler(request_pre_send, block_send)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(draft_mail.urls.send, follow=True)
    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT

    response = client.post(event.orga_urls.send_outbox, follow=True)
    assert response.status_code == 200
    draft_mail.refresh_from_db()
    assert draft_mail.state == QueuedMailStates.DRAFT

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


def test_compose_session_mail_preview(client, event, submission, other_submission):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        other_speaker = other_submission.speakers.select_related(
            "user", "event"
        ).first()

    response = client.post(
        event.orga_urls.compose_mails_sessions + "?state=submitted",
        data={
            **COMPOSE_DATA,
            "subject_0": "Preview {name}",
            "text_0": "Hello {submission_title}, see [{event_name}]({event_url})",
            "action": "preview",
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Subject:" in content
    assert (
        '<span class="placeholder" '
        'title="This value will be replaced based on dynamic parameters.">'
        "This Is a Proposal Title</span>"
    ) in content
    assert f'<a href="https://pretalx.com/{event.slug}/"' in content

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        data={
            **COMPOSE_DATA,
            "submissions": [submission.code],
            "speakers": [other_speaker.pk],
            "subject_0": "Preview",
            "text_0": "Hello {proposal_title}",
            "action": "preview",
        },
    )
    assert response.status_code == 200
    assert "Subject:" in response.content.decode()
    assert _mail_count(event) == 0


@pytest.mark.parametrize("item_count", (1, 3))
def test_compose_session_mail_preview_query_count(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        for _ in range(item_count):
            submission = SubmissionFactory(
                event=event, state=SubmissionStates.CONFIRMED
            )
            submission.speakers.add(SpeakerFactory(event=event))
            TalkSlotFactory(submission=submission, is_visible=True)
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    with django_assert_num_queries(21):
        response = client.post(
            event.orga_urls.compose_mails_sessions + "?state=confirmed",
            data={
                **COMPOSE_DATA,
                "subject_0": "Preview",
                "text_0": "Hello {submission_title} in {session_room}",
                "action": "preview",
            },
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Subject:" in content
    assert f"{item_count} email" in content


def test_compose_session_mail_preview_warns_about_managed_speakers(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        unreachable = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        submission.speakers.add(unreachable)
        other_submission = SubmissionFactory(event=event)
        managed = SpeakerFactory(
            event=event, user=None, email="managed@example.com", name="Managed"
        )
        other_submission.speakers.add(managed)

    response = client.post(
        event.orga_urls.compose_mails_sessions,
        data={
            **COMPOSE_DATA,
            "submissions": [submission.code, other_submission.code],
            "subject_0": "Preview",
            "text_0": "Please confirm: {confirmation_link}",
            "action": "preview",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "cannot receive this email" in content
    assert "No Mail" in content
    assert "only work with a pretalx account" in content
    assert "confirmation_link" in content
    assert "Managed" in content


@pytest.mark.parametrize(
    ("url_attr", "expected_title"),
    (("send_outbox", "Sending emails"), ("compose_mails_sessions", "Composing emails")),
)
def test_async_progress_page(
    client, event, settings, monkeypatch, url_attr, expected_title
):
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
