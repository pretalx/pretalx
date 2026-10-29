# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.core import mail as djmail
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.mail.models import QueuedMail
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def test_cfp_editor_changes_show_in_submission_form(client):
    event = EventFactory(cfp__fields={"duration": {"visibility": "do_not_ask"}})
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    editor_kwargs = {"event": event.slug, "step": "info"}

    response = client.get(event.cfp.urls.submit, follow=True)

    assert b"id_duration" not in response.content

    response = client.post(
        reverse("orga:cfp.editor.step", kwargs=editor_kwargs),
        {"title_0": "TEST CFP WOO", "text_0": "PLS SUBMIT HERE THX"},
    )
    assert response.status_code == 200
    response = client.post(
        reverse(
            "orga:cfp.editor.field_toggle", kwargs={**editor_kwargs, "action": "add"}
        ),
        {"field": "duration"},
    )
    assert response.status_code == 200
    response = client.post(
        reverse(
            "orga:cfp.editor.field", kwargs={**editor_kwargs, "field_key": "abstract"}
        ),
        {
            "visibility": "required",
            "min_length": "50",
            "max_length": "500",
            "label_0": "",
            "help_text_0": "",
        },
    )
    assert response.status_code == 200

    response = client.get(event.cfp.urls.submit, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "TEST CFP WOO" in content
    assert "PLS SUBMIT HERE THX" in content
    assert "id_duration" in content
    assert 'data-minlength="50"' in content
    assert 'data-maxlength="500"' in content

    response = client.post(
        reverse(
            "orga:cfp.editor.field_toggle", kwargs={**editor_kwargs, "action": "remove"}
        ),
        {"field": "duration"},
    )
    assert response.status_code == 200

    response = client.get(event.cfp.urls.submit, follow=True)

    assert b"id_duration" not in response.content


def test_question_create_and_remind_sends_mails(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_session_question,
        {
            "question_0": "What is your T-shirt size?",
            "variant": "string",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1

    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state="confirmed")
        submission.speakers.add(speaker)
        original_count = QueuedMail.objects.count()

    response = client.post(
        event.cfp.urls.remind_questions, {"role": "confirmed"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.count() == original_count + 1


def test_access_code_create_send_and_bypass_closed_cfp(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_access_code, {"code": "SPEAKERCODE"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="SPEAKERCODE")

    djmail.outbox = []
    response = client.post(
        code.urls.send,
        {
            "to": "invited@example.com",
            "text": "Please submit!",
            "subject": "Invitation",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    mail = djmail.outbox[0]
    assert mail.to == ["invited@example.com"]
    assert mail.subject == "Invitation"
    assert mail.body == "Please submit!"

    with scopes_disabled():
        event.cfp.deadline = now() - dt.timedelta(days=1)
        event.cfp.save()

    response = client.get(event.cfp.urls.submit, follow=True)

    assert b"id_title" not in response.content

    response = client.get(
        event.cfp.urls.submit + "?access_code=SPEAKERCODE", follow=True
    )

    assert response.status_code == 200
    assert b"id_title" in response.content


def test_submission_type_deadline_shown_on_cfp_text_page(client, event):
    with scopes_disabled():
        deadline = dt.datetime(2025, 6, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
        st = SubmissionTypeFactory(event=event, deadline=deadline)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.cfp.urls.edit_text)

    assert response.status_code == 200
    content = response.content.decode()
    assert str(st.name) in content
    assert "2025" in content
