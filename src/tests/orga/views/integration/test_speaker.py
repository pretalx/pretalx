# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
from urllib.parse import parse_qs, urljoin, urlparse

import pytest
from django import forms as django_forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
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
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_speaker_list_accessible_with_role_filter(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
    client.force_login(user)

    for query, expect_speaker in (
        ("", True),
        ("?role=speaker", True),
        ("?role=submitter", False),
        ("?role=foobar", True),  # invalid choice, filter_form is_valid()=False
    ):
        response = client.get(event.orga_urls.speakers + query, follow=True)

        assert response.status_code == 200
        name_present = speaker.get_display_name() in response.content.decode()
        assert name_present is expect_speaker, query


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
@pytest.mark.parametrize(
    ("columns", "num_queries"),
    ((None, 18), (["name", "has_arrived"], 14)),
    ids=("default_columns", "submissions_hidden"),
)
def test_speaker_list_query_count(
    client, event, item_count, columns, num_queries, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        if columns:
            user.get_event_preferences(event).set(
                "tables.SpeakerTable.columns", columns, commit=True
            )
        speakers = []
        submissions = []
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            speakers.append(speaker)
            for state, pending_state in (("submitted", "rejected"), ("accepted", None)):
                sub = SubmissionFactory(
                    event=event, state=state, pending_state=pending_state
                )
                sub.speakers.add(speaker)
                submissions.append(sub)
    client.force_login(user)

    with django_assert_num_queries(num_queries):
        response = client.get(event.orga_urls.speakers)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(s.get_display_name() in content for s in speakers)
    shown = columns is None
    assert all(
        (f'<a href="{sub.orga_urls.base}">{sub.title}</a>' in content) is shown
        for sub in submissions
    )
    assert ("submission-state-rejected" in content) is shown


def test_speaker_list_submissions_column_hides_unassigned_from_reviewer(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        track = TrackFactory(event=event)
        other_track = TrackFactory(event=event)
        reviewer.teams.get().limit_tracks.add(track)
        speaker = SpeakerFactory(event=event)
        visible = SubmissionFactory(event=event, track=track)
        hidden = SubmissionFactory(event=event, track=other_track)
        visible.speakers.add(speaker)
        hidden.speakers.add(speaker)
        draft = SubmissionFactory(event=event, state="draft")
        draft.speakers.add(speaker)
    client.force_login(reviewer)

    response = client.get(event.orga_urls.speakers)

    content = response.content.decode()
    assert response.status_code == 200
    assert visible.title in content
    assert hidden.title not in content
    assert draft.title not in content


def test_speaker_list_managed_indicator_and_dialog_actions(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        reachable = SpeakerFactory(
            event=event,
            user=None,
            name="Reachable Speaker",
            email="reachable@example.com",
        )
        unreachable = SpeakerFactory(
            event=event, user=None, name="Unreachable Speaker", email=None
        )
        pending = SpeakerFactory(
            event=event,
            user=None,
            name="Pending Speaker",
            email="pending@example.com",
            invitation_token="pendingtok1",
            invitation_sent=timezone.now(),
        )
        self_managed = SpeakerFactory(event=event, name="Account Speaker")
        for speaker in (reachable, unreachable, pending, self_managed):
            SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "status-dot" in content
    for speaker, dialog_text, invite, retract in (
        (reachable, "can receive emails at reachable@example.com", True, False),
        (
            unreachable,
            "cannot receive emails, as they have no contact email address",
            False,
            False,
        ),
        (pending, "is pending: it was sent on", True, True),
    ):
        assert speaker.name in content
        assert f'id="speaker-state-{speaker.code}"' in content
        assert dialog_text in content
        assert (speaker.orga_urls.retract_invitation in content) is retract
        assert (speaker.orga_urls.invite in content) is invite
    assert "Account Speaker" in content
    assert f"speaker-state-{self_managed.code}" not in content
    assert self_managed.orga_urls.retract_invitation not in content
    assert self_managed.orga_urls.invite not in content


def test_speaker_list_filters(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        account_speaker = SpeakerFactory(event=event, name="Account Speaker")
        SubmissionFactory(event=event).speakers.add(account_speaker)
        managed = SpeakerFactory(
            event=event, user=None, name="Findable Person", email="findable@example.com"
        )
        SubmissionFactory(event=event).speakers.add(managed)
        bare_orga = SpeakerFactory(
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
        account_backed = SpeakerFactory(
            event=event, name="Bare Account Speaker", origin=SpeakerProfileOrigin.ORGA
        )
    client.force_login(user)

    response = client.get(event.orga_urls.speakers, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert event.orga_urls.new_speaker in content
    assert "Account Speaker" in content
    assert "Findable Person" in content
    assert "Bare Orga Speaker" not in content
    assert "Bare CfP Speaker" not in content
    assert "Bare Account Speaker" not in content

    response = client.get(event.orga_urls.speakers + "?sessionless=on", follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Account Speaker" in content
    assert "Findable Person" in content
    assert "Bare Orga Speaker" in content
    assert "Bare CfP Speaker" not in content
    assert bare_orga.orga_urls.delete in content
    assert managed.orga_urls.delete not in content
    assert account_backed.orga_urls.delete not in content

    response = client.get(event.orga_urls.speakers + "?managed=true", follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Findable Person" in content
    assert "Account Speaker" not in content

    response = client.get(event.orga_urls.speakers + "?managed=false", follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Findable Person" not in content
    assert "Account Speaker" in content

    for query in ("findable@example.com", "Findable Person"):
        response = client.get(event.orga_urls.speakers + f"?q={query}", follow=True)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Findable Person" in content
        assert "Account Speaker" not in content


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


def test_speaker_detail_managed_speaker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event,
            user=None,
            name="Managed Speaker",
            biography="Old bio",
            origin=SpeakerProfileOrigin.ORGA,
        )
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Speaker",
            biography="Old bio",
            origin=SpeakerProfileOrigin.ORGA,
        )
        profile_count = SpeakerProfile.objects.filter(event=event).count()
        initial_logs = speaker.logged_actions().count()
    client.force_login(user)

    response = client.get(speaker.orga_urls.base, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert speaker.orga_urls.password_reset not in content
    assert speaker.orga_urls.delete not in content

    response = client.get(bare.orga_urls.base, follow=True)
    assert response.status_code == 200
    assert bare.orga_urls.delete in response.content.decode()

    response = client.get(speaker.orga_urls.password_reset, follow=True)
    assert response.status_code == 404

    for profile in (speaker, bare):
        response = client.post(
            profile.orga_urls.base,
            data={"name": "Updated Managed", "biography": "New bio"},
            follow=True,
        )
        assert response.status_code == 200
        with scopes_disabled():
            profile.refresh_from_db(fields=["name", "biography"])
            assert profile.name == "Updated Managed"
            assert profile.biography == "New bio"
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == profile_count

    response = client.post(speaker.orga_urls.toggle_arrived, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["has_arrived"])
        assert speaker.has_arrived is True
        assert speaker.logged_actions().count() == initial_logs + 2


def test_speaker_list_user_without_permission_gets_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)

    response = client.get(event.orga_urls.speakers)

    assert response.status_code == 404


def test_speaker_list_sort_by_question(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.STRING
        )
        AnswerFactory(question=question, speaker=speaker, answer="blue")
        other = SpeakerFactory(event=event, name="Apple Answerer")
        SubmissionFactory(event=event).speakers.add(other)
        AnswerFactory(question=question, speaker=other, answer="apple")

    client.force_login(user)

    response = client.get(
        event.orga_urls.speakers + f"?sort=question_{question.pk}", follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert content.index(other.get_display_name()) < content.index(
        speaker.get_display_name()
    )


def test_speaker_detail_accessible_by_orga(
    client, event, talk_slot, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        url = speaker.orga_urls.base
    client.force_login(user)
    ContentType.objects.clear_cache()

    with django_assert_num_queries(17):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    assert speaker.get_display_name() in response.content.decode()


def test_speaker_detail_edit_by_orga(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        account = speaker.user
        account_email = account.email
        original_name = "Original Name"
        speaker.name = original_name
        speaker.biography = "Stable bio"
        speaker.save(update_fields=["name", "biography"])
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event)
        other_sub.speakers.add(other_speaker)
        other_email = other_speaker.user.email
        url = speaker.orga_urls.base
        event.cfp.fields["availabilities"]["visibility"] = "do_not_ask"
        event.cfp.save()
        question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.STRING
        )
        choice_question = QuestionFactory(
            event=event, target="speaker", variant=QuestionVariant.CHOICES
        )
        for label in ("very", "incredibly", "omggreen"):
            AnswerOptionFactory(question=choice_question, answer=label)
        choice_answer = AnswerFactory(question=choice_question, speaker=speaker)
        chosen_option = choice_question.options.first()
        choice_answer.options.set([chosen_option])
        initial_log_count = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(
        url,
        data={
            "name": original_name,
            "biography": "Stable bio",
            "email": "",
            f"question_{choice_question.pk}": chosen_option.pk,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_log_count

    response = client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": "foo@foooobar.de",
            f"question_{question.pk}": "My speaker answer",
            f"question_{choice_question.pk}": chosen_option.pk,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["name", "email"])
        account.refresh_from_db(fields=["email"])
        assert speaker.name == "BESTSPEAKAR"
        assert speaker.email == "foo@foooobar.de"
        assert account.email == account_email
        logs = speaker.logged_actions()
        assert logs.count() == initial_log_count + 1
        log = logs.filter(action_type="pretalx.user.profile.update").get()
        assert log.person == user
        assert log.changes["name"]["old"] == original_name
        assert log.changes["name"]["new"] == "BESTSPEAKAR"
        assert not log.changes["email"]["old"]
        assert log.changes["email"]["new"] == "foo@foooobar.de"
        assert log.changes[f"question-{question.pk}"]["new"] == "My speaker answer"
        assert Answer.objects.filter(pk=choice_answer.pk).exists()

    response = client.post(
        url,
        data={
            "name": "BESTSPEAKAR",
            "biography": "I rule!",
            "email": other_email,
            f"question_{choice_question.pk}": "",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["email"])
        account.refresh_from_db(fields=["email"])
        assert speaker.email == other_email
        assert account.email == account_email
        assert not Answer.objects.filter(pk=choice_answer.pk).exists()
        QuestionFactory(
            event=event,
            target="speaker",
            variant=QuestionVariant.STRING,
            question_required=QuestionRequired.REQUIRED,
        )

    response = client.post(
        url,
        data={"name": "BLOCKED", "biography": "bio", "email": other_email},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["name"])
    assert speaker.name == "BESTSPEAKAR"


def test_speaker_detail_reviewer_cannot_edit(client, event, talk_slot):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
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
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
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


def test_speaker_password_reset(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        account = speaker.user
        url = speaker.orga_urls.password_reset

    client.force_login(user)

    response = client.get(url, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert speaker.get_display_name() in content
    assert account.email in content
    with scopes_disabled():
        account.refresh_from_db(fields=["pw_reset_token"])
    assert not account.pw_reset_token

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        account.refresh_from_db(fields=["pw_reset_token"])
    assert account.pw_reset_token


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "localhost", "port": 1},
        }
    },
    DEBUG=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_speaker_password_reset_shows_error_on_mail_failure(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        url = speaker.orga_urls.password_reset

    client.force_login(user)

    response = client.post(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "could not be sent" in content


def test_speaker_toggle_arrived(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
        url = speaker.orga_urls.toggle_arrived
        initial_logs = speaker.logged_actions().count()

    client.force_login(user)

    response = client.post(url + f"?next={event.orga_urls.speakers}")
    assert response.status_code == 302
    assert response.url == event.orga_urls.speakers
    with scopes_disabled():
        speaker.refresh_from_db(fields=["has_arrived"])
        assert speaker.has_arrived is True
        assert speaker.logged_actions().count() == initial_logs + 1
        assert speaker.logged_actions().first().action_type == "pretalx.speaker.arrived"

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["has_arrived"])
        assert speaker.has_arrived is False
        assert speaker.logged_actions().count() == initial_logs + 2
        assert (
            speaker.logged_actions().first().action_type == "pretalx.speaker.unarrived"
        )


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_information_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        infos = SpeakerInformationFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(17):
        response = client.get(event.orga_urls.information)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(info.title) in content for info in infos)


@pytest.mark.parametrize(
    ("user_kwargs", "list_status", "create_status"),
    (
        ({"can_change_event_settings": True}, 200, 200),
        ({"can_change_submissions": True}, 200, 404),
        ({"can_change_submissions": False, "is_reviewer": True}, 404, 404),
        (None, 404, 404),
    ),
    ids=("settings_orga", "submissions_orga", "reviewer", "unrelated_user"),
)
def test_speaker_information_access_by_role(
    client, event, user_kwargs, list_status, create_status
):
    with scopes_disabled():
        information = SpeakerInformationFactory(event=event)
        user = (
            UserFactory()
            if user_kwargs is None
            else make_orga_user(event, **user_kwargs)
        )
    client.force_login(user)

    list_response = client.get(event.orga_urls.information)
    create_response = client.get(event.orga_urls.new_information)

    assert list_response.status_code == list_status
    assert create_response.status_code == create_status
    if list_status == 200:
        assert str(information.title) in list_response.content.decode()


def test_speaker_information_anonymous_redirects_to_login(client, event):
    url = str(event.orga_urls.information)

    response = client.get(url)

    assert response.status_code == 302
    parsed = urlparse(response.url)
    assert parsed.path == str(event.orga_urls.login)
    assert parse_qs(parsed.query) == {"next": [url]}


def test_speaker_information_create_edit_and_delete(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        info = SpeakerInformationFactory(
            event=event, resource=SimpleUploadedFile("handbook.pdf", b"file content")
        )
        resource_url = info.resource.url
    client.force_login(user)

    response = client.get(event.orga_urls.information)
    assert response.status_code == 200
    assert f'href="{resource_url}"' in response.content.decode()

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
        created = event.information.exclude(pk=info.pk).get()
        assert str(created.title) == "Test Information"

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
        info.refresh_from_db(fields=["title"])
    assert str(info.title) == "Banana banana"

    response = client.post(info.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert list(event.information.all()) == [created]


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


def test_speaker_export(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
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
    data = {
        "target": "all",
        "name": "on",
        f"question_{question.pk}": "on",
        "submission_ids": "on",
    }

    response = client.post(
        event.orga_urls.speakers + "export/", data={**data, "export_format": "csv"}
    )
    assert response.status_code == 200
    assert "<!doctype" in response.content.decode().strip().lower()

    response = client.post(
        event.orga_urls.speakers + "export/",
        data={**data, "export_format": "csv", "data_delimiter": "comma"},
    )
    assert response.status_code == 200
    expected = (
        f"ID,Name,Proposal IDs,{question.question}\r\n"
        f"{speaker.code},{speaker.get_display_name()},{submission.code},{answer_string}\r\n"
    )
    # CSV exports start with a UTF-8 BOM so Excel detects the encoding.
    assert response.content.decode("utf-8-sig") == expected
    assert response.content.startswith(b"\xef\xbb\xbf")

    response = client.post(
        event.orga_urls.speakers + "export/", data={**data, "export_format": "json"}
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
        speaker = talk_slot.submission.speakers.select_related("user", "event").first()
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


def test_orga_speaker_invite_and_retract(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(
            event=event, user=None, name="Managed Speaker", email="managed@example.com"
        )
        SubmissionFactory(event=event).speakers.add(speaker)
    client.force_login(user)
    djmail.outbox = []

    response = client.post(speaker.orga_urls.retract_invitation, follow=True)
    assert response.status_code == 404

    response = client.get(speaker.orga_urls.invite, follow=True)
    assert response.status_code == 200
    assert "{invitation_link}" in response.context["form"].initial["text"]

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
        speaker.refresh_from_db(fields=["invitation_token"])
        assert speaker.invitation_token is None

    response = client.post(
        speaker.orga_urls.invite,
        {"subject": "Claim your profile", "text": "Here you go: {invitation_link}"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["invitation_token"])
        assert speaker.invitation_token
        assert len(djmail.outbox) == 1
        assert speaker.invitation_token in djmail.outbox[0].body
        assert djmail.outbox[0].to == ["managed@example.com"]
        mail = speaker.mails.get()
        assert mail.state == QueuedMailStates.SENT

    response = client.get(speaker.orga_urls.retract_invitation, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Managed Speaker" in content
    assert "managed@example.com" in content

    response = client.post(speaker.orga_urls.retract_invitation, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db(fields=["invitation_token"])
        assert speaker.invitation_token is None


def test_orga_speaker_invite_session_less_profile_errors(client, event):
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
        {
            "subject": "Claim your profile",
            "text": "About “{proposal_title}”: {invitation_link}",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert "text" in response.context["form"].errors

    response = client.post(
        speaker.orga_urls.invite,
        {"subject": "Claim your profile", "text": "Here you go: {invitation_link}"},
        follow=True,
    )
    assert response.status_code == 200
    assert response.context["form"].non_field_errors()

    assert len(djmail.outbox) == 0
    with scopes_disabled():
        speaker.refresh_from_db(fields=["invitation_token"])
        assert speaker.invitation_token is None


def test_orga_speaker_delete(client, event):
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
        mailless = SpeakerFactory(
            event=event,
            user=None,
            name="Mailless Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
    client.force_login(user)

    response = client.get(speaker.orga_urls.delete, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Historic Speaker (historic@example.com)" in content
    assert "removed permanently" in content
    assert "including all emails sent to this speaker" in content
    assert "marked as deleted" not in content

    response = client.get(mailless.orga_urls.delete, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Mailless Speaker" in content
    assert "Mailless Speaker (" not in content

    response = client.post(speaker.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=speaker.pk).exists()
        assert not event.queued_mails.filter(pk=mail.pk).exists()
        assert not SpeakerProfile.objects.filter(
            invitation_token="claim-me-token"
        ).exists()
        log = event.logged_actions().filter(action_type="pretalx.speaker.delete")
        assert log.count() == 1
        assert log.first().data["email"] == "historic@example.com"

    for query in ("", "?sessionless=on"):
        list_response = client.get(event.orga_urls.speakers + query, follow=True)
        assert list_response.status_code == 200
        assert "Historic Speaker" not in list_response.content.decode()

    search_response = client.get(event.orga_urls.speaker_search, {"search": "Historic"})
    assert json.loads(search_response.content.decode()) == {"count": 0, "results": []}


def test_orga_speaker_delete_and_invite_404_for_undeletable_profiles(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        with_session = SpeakerFactory(event=event, user=None)
        SubmissionFactory(event=event).speakers.add(with_session)
        account_backed = SpeakerFactory(event=event, origin=SpeakerProfileOrigin.ORGA)
    client.force_login(user)

    response = client.post(with_session.orga_urls.delete, follow=True)
    assert response.status_code == 404

    response = client.post(account_backed.orga_urls.delete, follow=True)
    assert response.status_code == 404

    response = client.get(account_backed.orga_urls.invite, follow=True)
    assert response.status_code == 404

    with scopes_disabled():
        assert (
            SpeakerProfile.objects.filter(
                pk__in=[with_session.pk, account_backed.pk]
            ).count()
            == 2
        )


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


def test_speaker_search(client, event, make_image):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)
        managed = SpeakerFactory(
            event=event,
            user=None,
            name="Findme Managed",
            origin=SpeakerProfileOrigin.ORGA,
        )
        shared_user = UserFactory(name="Findme Shared")
        shared = SpeakerFactory(event=event, user=shared_user)
        SubmissionFactory(event=event).speakers.add(shared)
        picture = ProfilePictureFactory(
            user=UserFactory(name="Findme Pictured"),
            avatar=make_image(),
            avatar_thumbnail_tiny=make_image("tiny.png"),
        )
        pictured = SpeakerFactory(
            event=event, user=picture.user, profile_picture=picture
        )
        SubmissionFactory(event=event).speakers.add(pictured)
        SpeakerFactory(
            event=event, user__name="Findme Hidden", origin=SpeakerProfileOrigin.CFP
        )
        other_event = EventFactory(organiser=event.organiser)
        for other_profile in (
            SpeakerFactory(
                event=other_event,
                user__name="Findme Remote",
                user__email="findme@example.com",
            ),
            SpeakerFactory(
                event=other_event,
                user=None,
                name="Findme Ghost",
                origin=SpeakerProfileOrigin.ORGA,
            ),
            SpeakerFactory(event=other_event, user=shared_user),
        ):
            SubmissionFactory(event=other_event).speakers.add(other_profile)
    client.force_login(user)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 4
    [group] = result["results"]
    assert (group["type"], group["label"]) == ("profile", "Speakers in this event")
    assert sorted(group["entries"], key=lambda entry: entry["name"]) == [
        {
            "code": profile.code,
            "name": "Findme Local",
            "avatar": None,
            "managed": False,
            "has_email": True,
        },
        {
            "code": managed.code,
            "name": "Findme Managed",
            "avatar": None,
            "managed": True,
            "has_email": False,
        },
        {
            "code": pictured.code,
            "name": "Findme Pictured",
            "avatar": urljoin(settings.SITE_URL, picture.avatar_thumbnail_tiny.url),
            "managed": False,
            "has_email": True,
        },
        {
            "code": shared.code,
            "name": "Findme Shared",
            "avatar": None,
            "managed": False,
            "has_email": True,
        },
    ]
    assert "findme@example.com" not in response.content.decode()

    response = client.get(event.orga_urls.speaker_search, {"search": "Fi"})
    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_speaker_search_denied_without_orga_access(client, event):
    with scopes_disabled():
        reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
        profile = SpeakerFactory(event=event, user__name="Findme Local")
        SubmissionFactory(event=event).speakers.add(profile)

    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})
    assert response.status_code == 302
    assert "login" in response.url

    client.force_login(reviewer)
    response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})
    assert response.status_code == 404


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

    with django_assert_num_queries(5):
        response = client.get(event.orga_urls.speaker_search, {"search": "Findme"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count
    assert "Findme Remote" not in response.content.decode()
    assert [len(group["entries"]) for group in data["results"]] == [item_count]


def test_speaker_create_without_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        account = UserFactory(email="account@example.com")
    client.force_login(user)
    djmail.outbox = []

    response = client.get(event.orga_urls.new_speaker, follow=True)
    assert response.status_code == 200
    assert "{invitation_link}" in response.context["form"]["invite_text"].initial
    assert event.orga_urls.speaker_search in response.text
    assert 'data-existing-selectable="false"' in response.text

    response = client.post(event.orga_urls.new_speaker, data={}, follow=False)
    assert response.status_code == 302
    assert response.url == event.orga_urls.speakers
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0

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
        no_mail = SpeakerProfile.objects.select_related("user", "event").get(
            event=event
        )
        assert no_mail.name == "No Mail Person"
        assert no_mail.email is None
        assert no_mail.user is None
        assert no_mail.origin == SpeakerProfileOrigin.ORGA
        assert list(no_mail.submissions.all()) == []
    assert response.redirect_chain[-1][0] == no_mail.orga_urls.base

    response = client.get(event.orga_urls.speakers + "?sessionless=on", follow=True)
    assert "No Mail Person" in response.text

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "Deferred Person", "email": "deferred@example.com"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        deferred = SpeakerProfile.objects.select_related("user", "event").get(
            event=event, email="deferred@example.com"
        )
        assert deferred.user is None
        assert deferred.invitation_token is None
    assert response.redirect_chain[-1][0] == deferred.orga_urls.base

    response = client.post(
        event.orga_urls.new_speaker,
        data={"name": "Other Name", "email": "deferred@example.com"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert set(SpeakerProfile.objects.filter(event=event)) == {no_mail, deferred}
        deferred.refresh_from_db(fields=["name", "invitation_token"])
        assert deferred.name == "Deferred Person"
        assert deferred.invitation_token is None
    assert response.redirect_chain[-1][0] == deferred.orga_urls.base

    response = client.post(
        event.orga_urls.new_speaker, data={"email": "account@example.com"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        managed = SpeakerProfile.objects.select_related("user", "event").get(
            event=event, email="account@example.com"
        )
        assert managed.user is None
        assert managed.user != account
        assert managed.origin == SpeakerProfileOrigin.ORGA
        assert managed.invitation_token is None
        assert event.queued_mails.count() == 0
    assert response.redirect_chain[-1][0] == managed.orga_urls.base
    assert len(djmail.outbox) == 0


def test_speaker_create_with_email_sends_claim_invite(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)
    djmail.outbox = []
    data = {
        "name": "New Person",
        "email": "newperson@example.com",
        "send_invite": "on",
        "invite_subject": "Claim your speaker profile",
    }

    response = client.post(
        event.orga_urls.new_speaker,
        data={**data, "invite_text": "About “{proposal_title}”: {invitation_link}"},
        follow=True,
    )
    assert response.status_code == 200
    assert "invite_text" in response.context["form"].errors
    assert len(djmail.outbox) == 0
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(event=event).count() == 0

    response = client.post(
        event.orga_urls.new_speaker,
        data={**data, "invite_text": "Please claim your profile: {invitation_link}"},
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        speaker = SpeakerProfile.objects.select_related("user", "event").get(
            event=event
        )
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
