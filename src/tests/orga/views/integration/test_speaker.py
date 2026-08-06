# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
from urllib.parse import urljoin

import pytest
from django import forms as django_forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.core import mail as djmail
from django.test import override_settings
from django.utils import timezone
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.enums import QueuedMailStates
from pretalx.orga.signals import speaker_form
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Answer
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    ProfilePictureFactory,
    QuestionFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("query", "expect_speaker"),
    (
        ("", True),
        ("?role=speaker", True),
        ("?role=submitter", False),
        ("?role=foobar", True),  # invalid choice, filter_form is_valid()=False
    ),
)
def test_speaker_list_accessible_with_role_filter(
    client, event, talk_slot, query, expect_speaker
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + query, follow=True)

    assert response.status_code == 200
    name_present = speaker.get_display_name() in response.content.decode()
    assert name_present is expect_speaker


def test_speaker_list_fulltext_search_finds_by_biography(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, biography="Unique quantum speaker bio")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

    client.force_login(user)
    bio_snippet = "Unique quantum"

    response = client.get(event.orga_urls.speakers + f"?q={bio_snippet}", follow=True)
    assert response.status_code == 200
    assert speaker.get_display_name() not in response.content.decode()

    response = client.get(
        event.orga_urls.speakers + f"?q={bio_snippet}&fulltext=on", follow=True
    )
    assert response.status_code == 200
    assert speaker.get_display_name() in response.content.decode()


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speakers = []
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event)
            sub.speakers.add(speaker)
            speakers.append(speaker)
    client.force_login(user)

    with django_assert_num_queries(17):
        response = client.get(event.orga_urls.speakers)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(s.get_display_name() in content for s in speakers)


@pytest.mark.parametrize(
    ("managed", "email", "token", "dialog_text", "invite", "retract"),
    (
        (
            True,
            "reachable@example.com",
            None,
            "can receive emails at reachable@example.com",
            True,
            False,
        ),
        (
            True,
            None,
            None,
            "cannot receive emails, as they have no contact email address",
            False,
            False,
        ),
        (
            True,
            "reachable@example.com",
            "pendingtok1",
            "is pending: it was sent on",
            True,
            True,
        ),
        (False, None, None, None, False, False),
    ),
    ids=["managed_reachable", "managed_unreachable", "invite_pending", "self_managed"],
)
def test_speaker_list_managed_indicator_and_dialog_actions(
    client, event, managed, email, token, dialog_text, invite, retract
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        kwargs = {"user": None} if managed else {}
        speaker = SpeakerFactory(
            event=event,
            name="Badge Speaker",
            email=email,
            invitation_token=token,
            invitation_sent=timezone.now() if token else None,
            **kwargs,
        )
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Badge Speaker" in content
    if managed:
        assert "status-dot" in content
        assert f'id="speaker-state-{speaker.code}"' in content
        assert dialog_text in content
    else:
        assert "status-dot" not in content
        assert "speaker-state-" not in content
    assert (speaker.orga_urls.retract_invitation in content) is retract
    assert (speaker.orga_urls.invite in content) is invite


def test_speaker_list_hides_sessionless_speakers_by_default(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, name="Speaker With Session")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        SpeakerFactory(
            event=event,
            user=None,
            name="Bare Orga Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)

    response = client.get(event.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Speaker With Session" in content
    assert "Bare Orga Speaker" not in content


def test_speaker_list_sessionless_toggle_reveals_only_non_cfp_profiles(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, name="Speaker With Session")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        SpeakerFactory(
            event=event,
            user=None,
            name="Bare Orga Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
        SpeakerFactory(
            event=event,
            user=None,
            name="Bare CfP Speaker",
            origin=SpeakerProfileOrigin.CFP,
        )
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + "?sessionless=on", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Speaker With Session" in content
    assert "Bare Orga Speaker" in content
    assert "Bare CfP Speaker" not in content


def test_speaker_list_and_detail_hide_bare_profiles_from_reviewers(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Orga Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(reviewer)

    list_response = client.get(
        event.orga_urls.speakers + "?sessionless=on", follow=True
    )
    detail_response = client.get(bare.orga_urls.base, follow=True)

    assert list_response.status_code == 200
    assert "Bare Orga Speaker" not in list_response.content.decode()
    assert detail_response.status_code == 404


def test_speaker_list_managed_filter(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        managed = SpeakerFactory(event=event, user=None, name="Managed Speaker")
        SubmissionFactory(event=event).speakers.add(managed)
        self_managed = SpeakerFactory(event=event, name="Account Speaker")
        SubmissionFactory(event=event).speakers.add(self_managed)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + "?managed=managed", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Managed Speaker" in content
    assert "Account Speaker" not in content

    response = client.get(
        event.orga_urls.speakers + "?managed=self-managed", follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Managed Speaker" not in content
    assert "Account Speaker" in content


@pytest.mark.parametrize("query", ("findable@example.com", "Findable Person"))
def test_speaker_list_search_finds_managed_speaker(client, event, query):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        managed = SpeakerFactory(
            event=event, user=None, name="Findable Person", email="findable@example.com"
        )
        SubmissionFactory(event=event).speakers.add(managed)
        other = SpeakerFactory(event=event, name="Other Speaker")
        SubmissionFactory(event=event).speakers.add(other)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + f"?q={query}", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Findable Person" in content
    assert "Other Speaker" not in content


@pytest.mark.parametrize("has_submission", (True, False))
def test_speaker_detail_edit_managed_speaker_saves_in_place(
    client, event, has_submission
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Managed Speaker",
            biography="Old bio",
            origin=SpeakerProfileOrigin.ORGA,
        )
        if has_submission:
            sub = SubmissionFactory(event=event)
            sub.speakers.add(speaker)
        profile_count = SpeakerProfile.objects.filter(event=event).count()
    client.force_login(user)

    response = client.post(
        speaker.orga_urls.base,
        data={"name": "Updated Managed", "biography": "New bio"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.name == "Updated Managed"
        assert speaker.biography == "New bio"
        assert SpeakerProfile.objects.filter(event=event).count() == profile_count


def test_speaker_password_reset_unavailable_for_managed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    client.force_login(user)

    detail = client.get(speaker.orga_urls.base, follow=True)
    reset = client.get(speaker.orga_urls.password_reset, follow=True)

    assert speaker.orga_urls.password_reset not in detail.content.decode()
    assert reset.status_code == 404


def test_speaker_toggle_arrived_managed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        initial_logs = speaker.logged_actions().count()
    client.force_login(user)

    response = client.post(speaker.orga_urls.toggle_arrived, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.has_arrived is True
        assert speaker.logged_actions().count() == initial_logs + 1


def test_speaker_list_user_without_permission_gets_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers)

    assert response.status_code == 404


def test_speaker_list_sort_by_question(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.STRING
        )
        AnswerFactory(question=question, speaker=speaker, answer="blue")

    client.force_login(user)

    response = client.get(
        event.orga_urls.speakers + f"?sort=question_{question.pk}", follow=True
    )

    assert response.status_code == 200


def test_speaker_detail_accessible_by_orga(
    client, event, talk_slot, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.base
    client.force_login(user)
    ContentType.objects.clear_cache()

    with django_assert_num_queries(18):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    assert speaker.get_display_name() in response.content.decode()


def test_speaker_detail_edit_by_orga(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        account_email = speaker.user.email
        url = speaker.orga_urls.base
        initial_log_count = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": "foo@foooobar.de",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        speaker.user.refresh_from_db()
    assert speaker.name == "BESTSPEAKAR"
    assert speaker.email == "foo@foooobar.de"
    assert speaker.user.email == account_email
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_log_count + 1
        log = (
            speaker.logged_actions()
            .filter(action_type="pretalx.user.profile.update")
            .first()
        )
        assert log.person == user
        assert not log.changes["email"]["old"]
        assert log.changes["email"]["new"] == "foo@foooobar.de"


def test_speaker_detail_edit_with_custom_field_consolidated_log(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, name="Original Name")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        url = speaker.orga_urls.base
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.STRING
        )
        initial_log_count = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(
        url,
        data={
            "name": "Updated Speaker Name",
            "biography": "Updated biography!",
            "email": speaker.user.email,
            f"question_{question.pk}": "My speaker answer",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        logs = speaker.logged_actions()
        assert logs.count() == initial_log_count + 1
        update_log = logs.filter(action_type="pretalx.user.profile.update").first()
        assert update_log
        assert update_log.changes["name"]["old"] == "Original Name"
        assert update_log.changes["name"]["new"] == "Updated Speaker Name"
        question_key = f"question-{question.pk}"
        assert update_log.changes[question_key]["new"] == "My speaker answer"


def test_speaker_detail_edit_unchanged_no_log(client):
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"availabilities": {"visibility": "do_not_ask"}}
        )
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event, name="Stable Name", biography="Stable bio"
        )
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        url = speaker.orga_urls.base
        initial_log_count = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(
        url,
        data={"name": speaker.name, "biography": speaker.biography, "email": ""},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_log_count


def test_speaker_detail_edit_clears_choice_question_answer(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, name="Speaker Name", biography="Bio")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        url = speaker.orga_urls.base
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.CHOICES
        )
        for label in ("very", "incredibly", "omggreen"):
            AnswerOptionFactory(question=question, answer=label)
        answer = AnswerFactory(question=question, speaker=speaker)
        answer.options.set([question.options.first()])

    client.force_login(user)

    response = client.post(
        url,
        data={
            "name": speaker.name,
            "biography": speaker.biography,
            "email": speaker.user.email,
            f"question_{question.pk}": "",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert not Answer.objects.filter(pk=answer.pk).exists()


def test_speaker_detail_edit_required_question_blocks_save(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.base
        QuestionFactory(
            event=event,
            target="speaker",
            variant=QuestionVariant.STRING,
            question_required=QuestionRequired.REQUIRED,
        )

    client.force_login(user)

    response = client.post(
        url,
        data={"name": "BESTSPEAKAR", "biography": "bio", "email": speaker.user.email},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.name != "BESTSPEAKAR"


def test_speaker_detail_edit_duplicate_email_accepted(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        account_email = speaker.user.email
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)
        url = speaker.orga_urls.base
        event.cfp.fields["availabilities"]["visibility"] = "do_not_ask"
        event.cfp.save()

    client.force_login(user)

    response = client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": other_speaker.user.email,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        speaker.user.refresh_from_db()
    assert speaker.name == "BESTSPEAKAR"
    assert speaker.email == other_speaker.user.email
    assert speaker.user.email == account_email


def test_speaker_detail_reviewer_cannot_edit(client, event, talk_slot):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.base

    client.force_login(reviewer)

    response = client.post(
        url, data={"name": "BESTSPEAKAR", "biography": "I rule!"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.name != "BESTSPEAKAR"


@pytest.mark.parametrize(
    ("user_kwargs", "visible"),
    (
        ({"can_change_submissions": True}, True),
        ({"can_change_submissions": False, "is_reviewer": True}, False),
    ),
    ids=("orga", "reviewer"),
)
def test_speaker_detail_internal_data_visible_only_to_orga(
    client, event, talk_slot, user_kwargs, visible
):
    with scopes_disabled():
        user = make_orga_user(event, **user_kwargs)
        speaker = talk_slot.submission.speakers.first()
        speaker.internal_notes = "ORGA INTERNAL SENTINEL NOTES"
        speaker.save()
        mail = QueuedMailFactory(
            event=event,
            subject="DECISION SENTINEL SUBJECT",
            text="DECISION SENTINEL BODY",
            state=QueuedMailStates.SENT,
        )
        mail.to_speakers.add(speaker)
        speaker_email = speaker.user.email
        url = speaker.orga_urls.base

    client.force_login(user)
    response = client.get(url, follow=True)
    content = response.content.decode()

    assert response.status_code == 200
    for secret in (
        "ORGA INTERNAL SENTINEL NOTES",
        "DECISION SENTINEL SUBJECT",
        "DECISION SENTINEL BODY",
        speaker_email,
    ):
        assert (secret in content) is visible


def test_speaker_password_reset_get_shows_confirmation(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.password_reset

    client.force_login(user)

    response = client.get(url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.user.refresh_from_db()
    assert not speaker.user.pw_reset_token


def test_speaker_password_reset_post_generates_token(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.password_reset

    client.force_login(user)

    response = client.post(url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.user.refresh_from_db()
    assert speaker.user.pw_reset_token


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_PORT=1,
    DEBUG=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_speaker_password_reset_shows_error_on_mail_failure(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.password_reset

    client.force_login(user)

    response = client.post(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "could not be sent" in content


def test_speaker_toggle_arrived(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.toggle_arrived
        initial_logs = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.has_arrived is True
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_logs + 1
        assert speaker.logged_actions().first().action_type == "pretalx.speaker.arrived"

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.has_arrived is False
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_logs + 2
        assert (
            speaker.logged_actions().first().action_type == "pretalx.speaker.unarrived"
        )


def test_speaker_toggle_arrived_respects_next_url(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.toggle_arrived

    client.force_login(user)

    response = client.post(url + f"?next={event.orga_urls.speakers}")

    assert response.status_code == 302
    assert response.url == event.orga_urls.speakers


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_information_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        SpeakerInformationFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.information)

    assert response.status_code == 200


def test_speaker_information_create(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        assert event.information.count() == 0
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_information,
        data={
            "title_0": "Test Information",
            "text_0": "Very Important!!!",
            "target_group": "submitters",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.information.count() == 1
        info = event.information.first()
        assert str(info.title) == "Test Information"


def test_speaker_information_edit(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        info = SpeakerInformationFactory(event=event)
    client.force_login(user)

    response = client.post(
        info.orga_urls.edit,
        data={
            "title_0": "Banana banana",
            "text_0": "Very Important!!!",
            "target_group": "submitters",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        info.refresh_from_db()
    assert str(info.title) == "Banana banana"


def test_speaker_information_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        info = SpeakerInformationFactory(event=event)
        assert event.information.count() == 1
    client.force_login(user)

    client.post(info.orga_urls.delete, follow=True)

    with scopes_disabled():
        assert event.information.count() == 0


def test_speaker_export_empty_redirects(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    client.force_login(user)
    export_url = event.orga_urls.speakers + "export/"

    response = client.post(
        export_url, data={"target": "accepted", "name": "on", "export_format": "json"}
    )

    assert response.status_code == 302
    assert response.url == export_url
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.WARNING]
    assert str(messages[0]) == "No data to be exported"


def test_speaker_export_csv_without_delimiter_returns_html(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = talk_slot.submission.speakers.first()
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.CHOICES
        )
        option = AnswerOptionFactory(question=question, answer="very")
        answer = AnswerFactory(
            question=question, submission=talk_slot.submission, speaker=speaker
        )
        answer.options.set([option])

    client.force_login(user)

    response = client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{question.pk}": "on",
            "export_format": "csv",
        },
    )

    assert response.status_code == 200
    assert "<!doctype" in response.content.decode().strip().lower()


def test_speaker_export_csv(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = talk_slot.submission.speakers.first()
        submission = talk_slot.submission
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.CHOICES
        )
        option = AnswerOptionFactory(question=question, answer="very")
        answer = AnswerFactory(
            question=question, submission=submission, speaker=speaker
        )
        answer.options.set([option])
        answer_string = answer.answer_string

    client.force_login(user)

    response = client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{question.pk}": "on",
            "submission_ids": "on",
            "export_format": "csv",
            "data_delimiter": "comma",
        },
    )

    assert response.status_code == 200
    expected = (
        f"ID,Name,Proposal IDs,{question.question}\r\n"
        f"{speaker.code},{speaker.get_display_name()},{submission.code},{answer_string}\r\n"
    )
    # CSV exports start with a UTF-8 BOM so Excel detects the encoding.
    assert response.content.decode("utf-8-sig") == expected
    assert response.content.startswith(b"\xef\xbb\xbf")


def test_speaker_export_json(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = talk_slot.submission.speakers.first()
        submission = talk_slot.submission
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.CHOICES
        )
        option = AnswerOptionFactory(question=question, answer="very")
        answer = AnswerFactory(
            question=question, submission=submission, speaker=speaker
        )
        answer.options.set([option])
        answer_string = answer.answer_string

    client.force_login(user)

    response = client.post(
        event.orga_urls.speakers + "export/",
        data={
            "target": "all",
            "name": "on",
            f"question_{question.pk}": "on",
            "submission_ids": "on",
            "export_format": "json",
        },
    )

    assert response.status_code == 200
    assert json.loads(response.content.decode()) == [
        {
            "ID": speaker.code,
            "Name": speaker.get_display_name(),
            question.question: answer_string,
            "Proposal IDs": [submission.code],
        }
    ]


class _ExtraSpeakerForm(django_forms.Form):
    extra_note = django_forms.CharField(required=False, initial="")

    def __init__(self, data=None, speaker=None, **kwargs):
        self.speaker = speaker
        super().__init__(data=data)

    def save(self):
        self.speaker.has_arrived = True
        self.speaker.save(update_fields=["has_arrived"])


def test_speaker_signal_extra_forms_saved_on_post(
    client, event, talk_slot, register_signal_handler
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.base

    def signal_receiver(signal, sender, request, instance, data=None, **kwargs):
        return _ExtraSpeakerForm(data=data, speaker=instance)

    register_signal_handler(speaker_form, signal_receiver)

    client.force_login(user)

    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert any(
        isinstance(f, _ExtraSpeakerForm) for f in response.context["extra_forms"]
    )

    assert speaker.has_arrived is False
    response = client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": speaker.user.email,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.has_arrived is True


def test_orga_speaker_invite_page_prefills_template(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None, email="managed@example.com")
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.get(speaker.orga_urls.invite, follow=True)

    assert response.status_code == 200
    form = response.context["form"]
    assert "{invitation_link}" in form.initial["text"]


def test_orga_speaker_invite_sends_directly(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None, email="managed@example.com")
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        speaker.orga_urls.invite,
        {"subject": "Claim your profile", "text": "Here you go: {invitation_link}"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert speaker.invitation_token in djmail.outbox[0].body
        assert djmail.outbox[0].to == ["managed@example.com"]
        mail = speaker.mails.get()
        assert mail.state == QueuedMailStates.SENT


def test_orga_speaker_invite_send_error_shows_form_error(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            email=None,
            name="No Mail",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        speaker.orga_urls.invite,
        {"subject": "Claim your profile", "text": "Here you go: {invitation_link}"},
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.invitation_token is None


def test_orga_speaker_invite_render_error_shows_form_error(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None, email="managed@example.com")
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        speaker.orga_urls.invite,
        {
            "subject": "Claim your profile",
            "text": "Broken placeholder: {does_not_exist}",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["form"].errors["text"]
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.invitation_token is None


def test_orga_speaker_invite_session_less_profile_rejects_proposal_placeholder(
    client, event
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            email="managed@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        speaker.orga_urls.invite,
        {
            "subject": "Claim your profile",
            "text": "About “{proposal_title}”: {invitation_link}",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "text" in response.context["form"].errors
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.invitation_token is None


def test_orga_speaker_invite_404_for_account_backed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.get(speaker.orga_urls.invite, follow=True)

    assert response.status_code == 404


def test_orga_speaker_retract_invitation(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            email="managed@example.com",
            invitation_token="orgatoken123",
        )
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.post(speaker.orga_urls.retract_invitation, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.invitation_token is None


def test_orga_speaker_retract_404_without_pending_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None, email="managed@example.com")
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.post(speaker.orga_urls.retract_invitation, follow=True)

    assert response.status_code == 404


def test_orga_speaker_retract_confirm_page(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Managed Speaker",
            email="managed@example.com",
            invitation_token="orgatoken123",
        )
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.get(speaker.orga_urls.retract_invitation, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Managed Speaker" in content
    assert "managed@example.com" in content


def test_orga_speaker_delete_confirm_page_single_wording(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            email="bare@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        mail.to_speakers.add(speaker)
    client.force_login(user)

    response = client.get(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "removed permanently" in content
    assert "including all emails sent to this speaker" in content
    assert "marked as deleted" not in content


def test_orga_speaker_delete_confirm_page_without_email_shows_plain_name(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Mailless Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)

    response = client.get(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Mailless Speaker" in content
    assert "Mailless Speaker (" not in content


def test_orga_speaker_delete_shreds_profile(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Orphan Speaker",
            email="orphan@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)

    response = client.post(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=speaker.pk).exists()
        log = event.logged_actions().filter(action_type="pretalx.speaker.delete")
        assert log.count() == 1
        assert log.first().data["email"] == "orphan@example.com"


def test_orga_speaker_delete_shreds_history_and_pending_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Historic Speaker",
            email="historic@example.com",
            invitation_token="claim-me-token",
            origin=SpeakerProfileOrigin.ORGA,
        )
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        mail.to_speakers.add(speaker)
    client.force_login(user)

    response = client.post(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=speaker.pk).exists()
        assert not event.queued_mails.filter(pk=mail.pk).exists()
        assert not SpeakerProfile.objects.filter(
            invitation_token="claim-me-token"
        ).exists()

    for query in ("", "?sessionless=on"):
        list_response = client.get(event.orga_urls.speakers + query, follow=True)
        assert list_response.status_code == 200
        assert "Historic Speaker" not in list_response.content.decode()

    search_response = client.get(event.orga_urls.speaker_search, {"search": "Historic"})
    assert json.loads(search_response.content.decode()) == {"count": 0, "results": []}


def test_orga_speaker_delete_404_for_profile_with_submissions(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, user=None)
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.post(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=speaker.pk).exists()


def test_orga_speaker_delete_404_for_account_backed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, origin=SpeakerProfileOrigin.ORGA)
    client.force_login(user)

    response = client.post(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=speaker.pk).exists()


def test_orga_speaker_delete_404_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        speaker = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.ORGA
        )
    client.force_login(reviewer)

    response = client.post(speaker.orga_urls.delete, follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=speaker.pk).exists()


def test_speaker_list_delete_action_only_on_deletable_rows(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        deletable = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.ORGA
        )
        with_session = SpeakerFactory(event=event, user=None)
        SubmissionFactory(event=event).speakers.add(with_session)
        account_backed = SpeakerFactory(event=event, origin=SpeakerProfileOrigin.ORGA)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + "?sessionless=on", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert deletable.orga_urls.delete in content
    assert with_session.orga_urls.delete not in content
    assert account_backed.orga_urls.delete not in content


def test_speaker_detail_delete_button_only_for_deletable(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        deletable = SpeakerFactory(
            event=event, user=None, origin=SpeakerProfileOrigin.ORGA
        )
        with_session = SpeakerFactory(event=event, user=None)
        SubmissionFactory(event=event).speakers.add(with_session)
    client.force_login(user)

    deletable_page = client.get(deletable.orga_urls.base, follow=True)
    with_session_page = client.get(with_session.orga_urls.base, follow=True)

    assert deletable.orga_urls.delete in deletable_page.content.decode()
    assert with_session.orga_urls.delete not in with_session_page.content.decode()


def test_speaker_search_offers_no_cross_event_data(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)
        other_event = EventFactory(organiser=event.organiser)
        other_profile = SpeakerFactory(
            event=other_event,
            user__name="Findme Remote",
            user__email="findme@example.com",
        )
        SubmissionFactory(event=other_event).speakers.add(other_profile)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "results": [
            {
                "type": "profile",
                "label": "Speakers in this event",
                "entries": [
                    {
                        "code": profile.code,
                        "name": "Findme Local",
                        "avatar": None,
                        "managed": False,
                        "has_email": True,
                    }
                ],
            }
        ],
    }
    assert "Findme Remote" not in response.content.decode()
    assert "findme@example.com" not in response.content.decode()


def test_speaker_search_includes_managed_profile_without_sessions(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        managed = SpeakerFactory(
            event=event,
            user=None,
            name="Findme Managed",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "results": [
            {
                "type": "profile",
                "label": "Speakers in this event",
                "entries": [
                    {
                        "code": managed.code,
                        "name": "Findme Managed",
                        "avatar": None,
                        "managed": True,
                        "has_email": False,
                    }
                ],
            }
        ],
    }


def test_speaker_search_excludes_cfp_profile_without_sessions(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        SpeakerFactory(
            event=event, user__name="Findme Hidden", origin=SpeakerProfileOrigin.CFP
        )
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_speaker_search_excludes_other_event_managed_profiles(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        other_event = EventFactory(organiser=event.organiser)
        managed = SpeakerFactory(
            event=other_event,
            user=None,
            name="Findme Ghost",
            origin=SpeakerProfileOrigin.ORGA,
        )
        SubmissionFactory(event=other_event).speakers.add(managed)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_speaker_search_shared_user_appears_only_as_event_profile(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        shared_user = UserFactory(name="Findme Shared")
        profile = SpeakerFactory(event=event, user=shared_user)
        SubmissionFactory(event=event).speakers.add(profile)
        other_event = EventFactory(organiser=event.organiser)
        other_profile = SpeakerFactory(event=other_event, user=shared_user)
        SubmissionFactory(event=other_event).speakers.add(other_profile)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "results": [
            {
                "type": "profile",
                "label": "Speakers in this event",
                "entries": [
                    {
                        "code": profile.code,
                        "name": "Findme Shared",
                        "avatar": None,
                        "managed": False,
                        "has_email": True,
                    }
                ],
            }
        ],
    }


def test_speaker_search_returns_avatar_thumbnail_url(client, event, make_image):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker_user = UserFactory(name="Findme Pictured")
        picture = ProfilePictureFactory(
            user=speaker_user,
            avatar=make_image(),
            avatar_thumbnail_tiny=make_image("tiny.png"),
        )
        profile = SpeakerFactory(
            event=event, user=speaker_user, profile_picture=picture
        )
        SubmissionFactory(event=event).speakers.add(profile)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    entry = response.json()["results"][0]["entries"][0]
    assert entry == {
        "code": profile.code,
        "name": "Findme Pictured",
        "avatar": urljoin(settings.SITE_URL, picture.avatar_thumbnail_tiny.url),
        "managed": False,
        "has_email": True,
    }


def test_speaker_search_short_query_returns_empty(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Fi"})

    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_speaker_search_not_accessible_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 404


def test_speaker_search_redirects_anonymous_to_login(client, event):
    with scopes_disabled():
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_search_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        other_event = EventFactory(organiser=event.organiser)
        for index in range(item_count):
            profile = SpeakerFactory(event=event, user__name=f"Findme Local {index}")
            SubmissionFactory(event=event).speakers.add(profile)
            other_profile = SpeakerFactory(
                event=other_event, user__name=f"Findme Remote {index}"
            )
            SubmissionFactory(event=other_event).speakers.add(other_profile)
    client.force_login(user)

    with django_assert_num_queries(6):
        response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count
    assert "Findme Remote" not in response.content.decode()
    assert [len(group["entries"]) for group in data["results"]] == [item_count]


def test_speaker_list_shows_add_speaker_button(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    assert event.orga_urls.new_speaker in response.text


def test_speaker_create_page_renders_form(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.new_speaker, follow=True)

    assert response.status_code == 200
    form = response.context["form"]
    assert "{invitation_link}" in form["invite_text"].initial
    assert event.orga_urls.speaker_search in response.text
    assert 'data-existing-selectable="false"' in response.text


def test_speaker_create_email_less_requires_confirmation(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_speaker, data={"name": "No Mail Person"}, follow=True
    )

    assert response.status_code == 200
    assert "confirm_email_less" in response.text
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "No Mail Person", "confirm_email_less": "on"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker = SpeakerProfile.objects.get(event=event)
        assert speaker.name == "No Mail Person"
        assert speaker.email is None
        assert speaker.user is None
        assert speaker.origin == SpeakerProfileOrigin.ORGA
        assert list(speaker.submissions.all()) == []
    assert response.redirect_chain[-1][0] == speaker.orga_urls.base

    response = client.get(event.orga_urls.speakers + "?sessionless=on", follow=True)
    assert "No Mail Person" in response.text


def test_speaker_create_with_email_sends_claim_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.new_speaker,
        data={
            "name": "New Person",
            "email": "newperson@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your speaker profile",
            "invite_text": "Please claim your profile: {invitation_link}",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker = SpeakerProfile.objects.get(event=event)
        assert speaker.name == "New Person"
        assert speaker.email == "newperson@example.com"
        assert speaker.user is None
        assert speaker.origin == SpeakerProfileOrigin.ORGA
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ["newperson@example.com"]
        assert speaker.invitation_token in djmail.outbox[0].body
        create_log = speaker.logged_actions().filter(
            action_type="pretalx.speaker.create"
        )
        assert create_log.count() == 1
        assert create_log.first().person == user
    assert response.redirect_chain[-1][0] == speaker.orga_urls.base


def test_speaker_create_with_email_without_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "Deferred Person", "email": "deferred@example.com"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker = SpeakerProfile.objects.get(event=event)
        assert speaker.email == "deferred@example.com"
        assert speaker.user is None
        assert speaker.invitation_token is None
    assert len(djmail.outbox) == 0


def test_speaker_create_matching_event_profile_no_duplicate(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        existing = SpeakerFactory(
            event=event,
            user=None,
            email="managed@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "Other Name", "email": "managed@example.com"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert list(SpeakerProfile.objects.filter(event=event)) == [existing]
        existing.refresh_from_db()
        assert existing.invitation_token is None
    assert len(djmail.outbox) == 0
    assert response.redirect_chain[-1][0] == existing.orga_urls.base


def test_speaker_create_account_email_creates_managed_profile(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        account = UserFactory(email="account@example.com")
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.new_speaker, data={"email": "account@example.com"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker = SpeakerProfile.objects.get(event=event)
        assert speaker.user is None
        assert speaker.user != account
        assert speaker.email == "account@example.com"
        assert speaker.origin == SpeakerProfileOrigin.ORGA
        assert speaker.invitation_token is None
        assert event.queued_mails.count() == 0
    assert len(djmail.outbox) == 0
    assert response.redirect_chain[-1][0] == speaker.orga_urls.base


def test_speaker_create_rejects_proposal_placeholders(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        event.orga_urls.new_speaker,
        data={
            "name": "New Person",
            "email": "newperson@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your speaker profile",
            "invite_text": "About “{proposal_title}”: {invitation_link}",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "invite_text" in response.context["form"].errors
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0


def test_speaker_create_empty_form_redirects_to_speaker_list(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.post(event.orga_urls.new_speaker, data={}, follow=False)

    assert response.status_code == 302
    assert response.url == event.orga_urls.speakers
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0


def test_speaker_create_invite_send_error_rolls_back(client, event, monkeypatch):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []

    def explode(*args, **kwargs):
        raise SendMailException("nope")

    monkeypatch.setattr("pretalx.orga.forms.submission.send_speaker_invite", explode)

    response = client.post(
        event.orga_urls.new_speaker,
        data={
            "name": "New Person",
            "email": "newperson@example.com",
            "send_invite": "on",
            "invite_subject": "Claim your speaker profile",
            "invite_text": "Claim it: {invitation_link}",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0


def test_speaker_create_not_accessible_for_reviewer(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.new_speaker)
    assert response.status_code == 404

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "Sneaky Person", "confirm_email_less": "on"},
    )
    assert response.status_code == 404
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0
