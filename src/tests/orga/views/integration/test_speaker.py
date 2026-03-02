# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django import forms as django_forms
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django_scopes import scopes_disabled

from pretalx.orga.signals import speaker_form
from pretalx.submission.models import Answer
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("query", ("", "?role=true", "?role=false", "?role=foobar"))
def test_speaker_list_accessible_with_role_filter(client, event, talk_slot, query):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
    client.force_login(user)

    response = client.get(event.orga_urls.speakers + query, follow=True)

    assert response.status_code == 200
    if not query:
        assert speaker.get_display_name() in response.content.decode()


def test_speaker_list_fulltext_search_finds_by_biography(client, event):
    """Biography search only works when fulltext flag is enabled."""
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

    with django_assert_num_queries(21):
        response = client.get(event.orga_urls.speakers)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(s.get_display_name() in content for s in speakers)


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

    with django_assert_num_queries(22):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    assert speaker.get_display_name() in response.content.decode()


def test_speaker_detail_edit_by_orga(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
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
    assert speaker.user.email == "foo@foooobar.de"
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_log_count + 1


def test_speaker_detail_edit_with_custom_field_consolidated_log(client, event):
    """Editing speaker profile and question answer creates a single consolidated log."""
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
        data={
            "name": speaker.name,
            "biography": speaker.biography,
            "email": speaker.user.email,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert speaker.logged_actions().count() == initial_log_count


def test_speaker_detail_edit_clears_choice_question_answer(client, event):
    """Submitting an empty choice question answer removes the Answer object."""
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


def test_speaker_detail_edit_duplicate_email_rejected(client, event, talk_slot):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
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
    assert speaker.name != "BESTSPEAKAR"
    assert speaker.user.email != other_speaker.user.email


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
    """When the reset email cannot be sent, an error message is shown."""
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
    """Toggle arrived flips has_arrived and creates log entries."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = talk_slot.submission.speakers.first()
        url = speaker.orga_urls.toggle_arrived
        initial_logs = speaker.user.logged_actions().count()

    client.force_login(user)

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.has_arrived is True
    with scopes_disabled():
        assert speaker.user.logged_actions().count() == initial_logs + 1

    response = client.post(url, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
    assert speaker.has_arrived is False
    with scopes_disabled():
        assert speaker.user.logged_actions().count() == initial_logs + 2


def test_speaker_toggle_arrived_respects_next_url(client, event, talk_slot):
    """Toggle arrived redirects to the 'next' URL when provided."""
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

    with django_assert_num_queries(20):
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


def test_speaker_export_csv_without_delimiter_returns_html(client, event, talk_slot):
    """CSV export of choice question without delimiter returns HTML error."""
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
    """CSV export produces correct headers and data."""
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
    assert response.content.decode() == expected


def test_speaker_export_json(client, event, talk_slot):
    """JSON export produces correct structure and data."""
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
    """Real Django form returned by a test signal handler to verify
    FormSignalMixin integration (renders on GET, saves on POST)."""

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
    """Extra forms from the speaker_form signal are rendered and saved."""
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
