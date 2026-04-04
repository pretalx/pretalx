# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from io import BytesIO
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pytest
from django.core import mail as djmail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event
from pretalx.mail.models import QueuedMail
from pretalx.submission.models import Question, QuestionTarget
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def question(event):
    with scopes_disabled():
        return QuestionFactory(
            event=event,
            question="How much do you like green?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            position=1,
        )


@pytest.fixture
def inactive_question(event):
    with scopes_disabled():
        return QuestionFactory(
            event=event,
            question="How much do you like red?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            active=False,
            position=2,
        )


@pytest.fixture
def choice_question(event):
    with scopes_disabled():
        q = QuestionFactory(
            event=event,
            question="How much do you like green?",
            variant=QuestionVariant.CHOICES,
            target="speaker",
            position=9,
        )
        for answer in ("very", "incredibly", "omggreen"):
            AnswerOptionFactory(question=q, answer=answer)
    return q


@pytest.fixture
def answered_choice_question(event, choice_question):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        a = AnswerFactory(
            submission=submission, question=choice_question, speaker=speaker
        )
        a.options.set([choice_question.options.first()])
    return choice_question


@pytest.fixture
def file_question(event):
    with scopes_disabled():
        return QuestionFactory(
            event=event,
            question="Please submit your paper.",
            variant=QuestionVariant.FILE,
            target="submission",
            position=7,
        )


@pytest.fixture
def speaker_file_question(event):
    with scopes_disabled():
        return QuestionFactory(
            event=event,
            question="Please submit your CV.",
            variant=QuestionVariant.FILE,
            target="speaker",
            position=8,
        )


@pytest.fixture
def speaker_question(event):
    with scopes_disabled():
        return QuestionFactory(
            event=event,
            question="What is your favourite color?",
            variant=QuestionVariant.STRING,
            target="speaker",
            position=3,
        )


@pytest.fixture
def submission_type(event):
    with scopes_disabled():
        return SubmissionTypeFactory(event=event, name="Workshop", default_duration=60)


@pytest.fixture
def track(event):
    # use_tracks is True by default in EventFactory
    with scopes_disabled():
        return TrackFactory(event=event, name="Test Track")


@pytest.fixture
def access_code(event):
    with scopes_disabled():
        return SubmitterAccessCodeFactory(event=event)


@pytest.fixture
def remind_submissions(event):
    """Two submissions for role-filtered reminder tests: one confirmed, one submitted."""
    with scopes_disabled():
        speaker1 = SpeakerFactory(event=event)
        confirmed_sub = SubmissionFactory(event=event, state="confirmed")
        confirmed_sub.speakers.add(speaker1)

        speaker2 = SpeakerFactory(event=event)
        submitted_sub = SubmissionFactory(event=event, state="submitted")
        submitted_sub.speakers.add(speaker2)
    return confirmed_sub, speaker1, submitted_sub, speaker2


def test_cfp_text_get_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.cfp.urls.edit_text)

    assert response.status_code == 200
    assert b"deadline" in response.content


def test_cfp_text_anonymous_redirects(client, event):
    response = client.get(event.cfp.urls.edit_text)

    assert response.status_code == 302
    assert "/login/" in response.url


def test_cfp_text_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.cfp.urls.edit_text)

    assert response.status_code == 404


def test_cfp_text_post_updates_cfp(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.cfp.urls.edit_text,
        {
            "headline_0": "new headline",
            "text_0": "",
            "deadline": "2000-10-10 20:20",
            "count_length_in": "chars",
            "settings-cfp_ask_abstract": "required",
            "settings-cfp_ask_description": "do_not_ask",
            "settings-cfp_ask_notes": "optional",
            "settings-cfp_ask_biography": "optional",
            "settings-cfp_ask_avatar": "optional",
            "settings-cfp_ask_availabilities": "optional",
            "settings-cfp_ask_do_not_record": "optional",
            "settings-cfp_ask_image": "optional",
            "settings-cfp_ask_track": "optional",
            "settings-cfp_ask_duration": "optional",
            "settings-cfp_ask_additional_speaker": "optional",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    assert str(event.cfp.headline) == "new headline"


def test_cfp_text_timezone_display(client):
    """CfP deadline is displayed in the event's timezone."""
    event = EventFactory(
        timezone="Europe/Berlin",
        cfp__deadline=dt.datetime(2018, 3, 5, 17, 39, 15, tzinfo=ZoneInfo("UTC")),
    )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.cfp.urls.edit_text)

    assert response.status_code == 200
    content = response.content.decode()
    assert "2018-03-05T18:39" in content
    assert "2018-03-05T17:39" not in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_question_list_shows_questions(
    client, event, django_assert_num_queries, item_count
):
    """Question list shows active and inactive questions with constant query count."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    with scopes_disabled():
        questions = QuestionFactory.create_batch(item_count, event=event)
        inactive = QuestionFactory(event=event, active=False)
    client.force_login(user)

    with django_assert_num_queries(20):
        response = client.get(event.cfp.urls.questions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    for q in questions:
        assert str(q.question) in content
    assert str(inactive.question) in content


@pytest.mark.parametrize("role", ("accepted", ""))
def test_question_detail_accessible_with_role_filter(client, event, question, role):
    """Legacy coverage: the question detail view renders with role filter params."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    url = question.urls.base + (f"?role={role}" if role else "")
    response = client.get(url, follow=True)

    assert response.status_code == 200
    assert str(question.question) in response.content.decode()


def test_question_create_simple(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "Please answer!",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1
        q = event.questions.first()
        assert str(q.question) == "What is your name?"
        assert q.variant == "string"


def test_question_create_with_freeze_after(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.REQUIRED,
            "freeze_after": "2021-06-22T12:44:42Z",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1


def test_question_create_after_deadline(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.AFTER_DEADLINE,
            "deadline": "2021-06-22T12:44:42Z",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1
        q = event.questions.first()
        assert q.deadline == dt.datetime(
            2021, 6, 22, 12, 44, 42, tzinfo=ZoneInfo("UTC")
        )


def test_question_create_after_deadline_missing_deadline_fails(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.AFTER_DEADLINE,
        },
        follow=True,
    )

    with scopes_disabled():
        assert event.questions.count() == 0


def test_question_create_choice(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "Is it African or European?",
            "variant": "choices",
            "active": True,
            "help_text_0": "",
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 0,
            "form-0-id": "",
            "form-0-answer_0": "African",
            "form-1-id": "",
            "form-1-answer_0": "European",
            "form-2-id": "",
            "form-2-answer_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1
        q = event.questions.first()
        assert q.variant == "choices"
        assert q.options.count() == 2


def test_question_edit_choice_options(client, event, choice_question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = choice_question.options.count()
        first_option = choice_question.options.first()
        last_option = choice_question.options.last()
        other_option = choice_question.options.all()[1]

    response = client.post(
        choice_question.urls.edit,
        {
            "target": "submission",
            "question_0": "Is it African or European?",
            "variant": "choices",
            "active": True,
            "help_text_0": "",
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 3,
            "form-0-id": first_option.pk,
            "form-0-answer_0": "African",
            "form-1-id": last_option.pk,
            "form-1-answer_0": "European",
            "form-2-id": other_option.pk,
            "form-2-answer_0": str(other_option.answer),
            "form-2-DELETE": "on",
            "form-3-id": "",
            "form-3-answer_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert choice_question.options.count() == count - 1
        assert str(choice_question.options.first().answer) == "African"


def test_question_delete(client, event, question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(question.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 1

    response = client.post(question.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.questions.count() == 0
        assert Question.all_objects.filter(event=event).count() == 0


def test_question_delete_inactive(client, event, inactive_question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(inactive_question.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert Question.all_objects.filter(event=event).count() == 0


def test_question_delete_answered_deactivates_instead(
    client, event, answered_choice_question
):
    """Answered questions cannot be deleted, only deactivated."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(answered_choice_question.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        q = Question.all_objects.get(pk=answered_choice_question.pk)
        assert not q.active
        assert q.answers.count() == 1
        assert q.options.count() == 3


def test_question_toggle_deactivate(client, event, question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    assert question.active

    response = client.get(question.urls.toggle, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        q = Question.all_objects.get(pk=question.pk)
        assert not q.active


def test_question_toggle_activate(client, event, inactive_question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(inactive_question.urls.toggle, follow=True)

    assert response.status_code == 200
    inactive_question.refresh_from_db()
    assert inactive_question.active


@pytest.mark.parametrize(
    ("role", "count"), (("accepted", 1), ("confirmed", 1), ("", 2))
)
def test_question_remind_submission_question(
    client, event, question, remind_submissions, role, count
):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        original_count = QueuedMail.objects.count()

    response = client.post(event.cfp.urls.remind_questions, {"role": role}, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.count() == original_count + count


def test_question_remind_multiple_questions(
    client, event, question, speaker_question, remind_submissions
):
    """Reminders with both submission and speaker questions send one mail per speaker."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        original_count = QueuedMail.objects.count()

    response = client.post(event.cfp.urls.remind_questions, {"role": ""}, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert QueuedMail.objects.count() == original_count + 2


def test_question_remind_answered_does_not_send(
    client, event, question, remind_submissions
):
    """No reminder sent when questions are already answered."""
    confirmed_sub, _, submitted_sub, _ = remind_submissions
    with scopes_disabled():
        AnswerFactory(submission=confirmed_sub, question=question, answer="something")
        AnswerFactory(submission=submitted_sub, question=question, answer="something")
        original_count = QueuedMail.objects.count()
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    client.post(event.cfp.urls.remind_questions, {"role": ""}, follow=True)

    with scopes_disabled():
        assert QueuedMail.objects.count() == original_count


def test_question_remind_invalid_role(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        event.cfp.urls.remind_questions, {"role": "hahaha"}, follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Could not send mails" in content


def test_question_file_download_non_file_redirects(client, event, question):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(question.urls.download, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "does not support file downloads" in content


def test_question_file_download_creates_cached_file(client, event, file_question):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        answer = AnswerFactory(
            submission=submission, question=file_question, answer="doc.pdf"
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"pdf content"))
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    initial_count = CachedFile.objects.count()

    response = client.get(file_question.urls.download, follow=False)

    assert response.status_code == 200
    assert CachedFile.objects.count() == initial_count + 1


def test_question_file_download_generates_zip(client, event, file_question):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
        answer = AnswerFactory(
            submission=submission, question=file_question, answer="test.txt"
        )
        answer.answer_file.save("test.txt", ContentFile(b"test content"))
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(file_question.urls.download)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert submission.code in names[0]
        assert zf.read(names[0]) == b"test content"


def test_question_file_download_duplicate_filenames(client, event):
    with scopes_disabled():
        file_question = QuestionFactory(
            event=event,
            question="Upload file",
            variant=QuestionVariant.FILE,
            target="submission",
        )
        speaker = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event)
        sub1.speakers.add(speaker)
        sub2 = SubmissionFactory(event=event)
        sub2.speakers.add(speaker)
        a1 = AnswerFactory(submission=sub1, question=file_question, answer="same.txt")
        a1.answer_file.save("same.txt", ContentFile(b"content 1"))
        a2 = AnswerFactory(submission=sub2, question=file_question, answer="same.txt")
        a2.answer_file.save("same.txt", ContentFile(b"content 2"))
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(file_question.urls.download)

    assert response.status_code == 200
    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        contents = {zf.read(name) for name in names}
        assert contents == {b"content 1", b"content 2"}


def test_question_file_download_speaker_question(client, event, speaker_file_question):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        answer = AnswerFactory(
            question=speaker_file_question, speaker=speaker, answer="cv.pdf"
        )
        answer.answer_file.save("cv.pdf", ContentFile(b"CV content"))
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(speaker_file_question.urls.download)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert speaker.code in names[0]
        assert zf.read(names[0]) == b"CV content"


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_type_list_query_count(
    client, event, django_assert_num_queries, item_count
):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    with scopes_disabled():
        types = SubmissionTypeFactory.create_batch(item_count - 1, event=event)
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(event.cfp.urls.types)

    assert response.status_code == 200
    content = response.content.decode()
    for st in types:
        assert str(st.name) in content


def test_submission_type_make_default(client, event, submission_type):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        assert event.cfp.default_type != submission_type

    response = client.get(submission_type.urls.default, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        event.cfp.refresh_from_db()
        assert event.cfp.default_type == submission_type


def test_submission_type_edit(client, event, submission_type):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = submission_type.logged_actions().count()

    response = client.post(
        submission_type.urls.edit,
        {"default_duration": 31, "slug": "New_Type", "name_0": "New Type!"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert submission_type.logged_actions().count() == count + 1
        submission_type.refresh_from_db()
    assert submission_type.default_duration == 31
    assert str(submission_type.name) == "New Type!"


def test_submission_type_edit_without_change_no_log(client, event, submission_type):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = submission_type.logged_actions().count()

    client.post(
        submission_type.urls.edit,
        {
            "default_duration": submission_type.default_duration,
            "slug": submission_type.slug,
            "name_0": str(submission_type.name),
        },
        follow=True,
    )

    with scopes_disabled():
        assert submission_type.logged_actions().count() == count


def test_submission_type_delete(client, event, submission_type):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        assert event.submission_types.count() == 2

    response = client.get(submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.submission_types.count() == 2

    response = client.post(submission_type.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submission_types.count() == 1


def test_submission_type_delete_used_fails(client, event, submission_type):
    """Cannot delete a submission type that has submissions."""
    with scopes_disabled():
        SubmissionFactory(event=event, submission_type=submission_type)
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(submission_type.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submission_types.count() == 2


def test_submission_type_delete_last_fails(client, event):
    """Cannot delete the last remaining submission type."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        last_type = event.cfp.default_type
        assert event.submission_types.count() == 1

    response = client.post(last_type.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submission_types.count() == 1


def test_submission_type_delete_default_fails(client, event, submission_type):
    """Cannot delete the default submission type."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        default = event.cfp.default_type

    response = client.post(default.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submission_types.count() == 2


@pytest.mark.parametrize("item_count", (1, 3))
def test_track_list_query_count(client, event, django_assert_num_queries, item_count):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    with scopes_disabled():
        tracks = TrackFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(17):
        response = client.get(event.cfp.urls.tracks)

    assert response.status_code == 200
    content = response.content.decode()
    for t in tracks:
        assert str(t.name) in content


def test_track_detail_accessible(client, event, track):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(track.urls.base)

    assert response.status_code == 200
    assert str(track.name) in response.content.decode()


def test_track_edit(client, event, track):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = track.logged_actions().count()

    response = client.post(
        track.urls.base, {"name_0": "Renamed", "color": "#ffff99"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert track.logged_actions().count() == count + 1
        track.refresh_from_db()
    assert str(track.name) == "Renamed"


def test_track_edit_without_change_no_log(client, event, track):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = track.logged_actions().count()

    client.post(
        track.urls.base, {"name_0": str(track.name), "color": track.color}, follow=True
    )

    with scopes_disabled():
        assert track.logged_actions().count() == count


def test_track_edit_invalid_color_rejected(client, event, track):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    client.post(track.urls.base, {"name_0": "Name", "color": "#fgff99"}, follow=True)

    track.refresh_from_db()
    assert str(track.name) != "Name"


def test_track_delete(client, event, track):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(track.urls.delete)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.tracks.count() == 1

    response = client.post(track.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.tracks.count() == 0


def test_track_delete_used_fails(client, event, track):
    """Cannot delete a track that has submissions."""
    with scopes_disabled():
        SubmissionFactory(event=event, track=track)
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(track.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.tracks.count() == 1


@pytest.mark.parametrize("item_count", (1, 3))
def test_access_code_list_query_count(
    client, event, django_assert_num_queries, item_count
):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    with scopes_disabled():
        codes = SubmitterAccessCodeFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(19):
        response = client.get(event.cfp.urls.access_codes)

    assert response.status_code == 200
    content = response.content.decode()
    for code in codes:
        assert code.code in content


def test_access_code_detail_accessible(client, event, access_code):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(access_code.urls.edit)

    assert response.status_code == 200
    assert access_code.code in response.content.decode()


def test_access_code_create(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(event.cfp.urls.new_access_code, follow=True)
    assert response.status_code == 200

    response = client.post(
        event.cfp.urls.new_access_code, {"code": "LOLCODE"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submitter_access_codes.get(code="LOLCODE")


def test_access_code_create_forbidden_characters_rejected(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    client.post(event.cfp.urls.new_access_code, {"code": "LOL %CODE"}, follow=True)

    with scopes_disabled():
        assert event.submitter_access_codes.all().count() == 0


def test_access_code_edit(client, event, access_code):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = access_code.logged_actions().count()

    response = client.post(access_code.urls.edit, {"code": "LOLCODE"}, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        access_code.refresh_from_db()
        assert access_code.logged_actions().count() == count + 1
    assert access_code.code == "LOLCODE"


def test_access_code_edit_without_change_no_log(client, event, access_code):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        count = access_code.logged_actions().count()

    client.post(
        access_code.urls.edit,
        {"code": access_code.code, "maximum_uses": access_code.maximum_uses},
        follow=True,
    )

    with scopes_disabled():
        assert access_code.logged_actions().count() == count


def test_access_code_delete(client, event, access_code):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(access_code.urls.delete)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.submitter_access_codes.count() == 1

    response = client.post(access_code.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submitter_access_codes.count() == 0


def test_access_code_delete_used_fails(client, event, access_code):
    """Cannot delete an access code used by a submission."""
    with scopes_disabled():
        SubmissionFactory(event=event, access_code=access_code)
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(access_code.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.submitter_access_codes.count() == 1


def test_access_code_send(client, event, access_code):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    djmail.outbox = []

    response = client.get(access_code.urls.send, follow=True)
    assert response.status_code == 200

    response = client.post(
        access_code.urls.send,
        {"to": "test@example.com", "text": "test test", "subject": "test"},
        follow=True,
    )

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    mail = djmail.outbox[0]
    assert mail.to == ["test@example.com"]
    assert mail.body == "test test"
    assert mail.subject == "test"


def test_access_code_send_with_restrictions(client, event, access_code, track):
    """Sending an access code with validity/usage restrictions works."""
    with scopes_disabled():
        access_code.valid_until = event.datetime_from
        access_code.maximum_uses = 3
        access_code.save()
        access_code.tracks.add(track)
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.get(access_code.urls.send, follow=True)

    assert response.status_code == 200


def test_cfp_editor_main_view(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.cfp.urls.editor)

    assert response.status_code == 200
    assert b"submission-steps" in response.content


@pytest.mark.parametrize("step", ("info", "questions", "user", "profile"))
def test_cfp_editor_step_view(client, event, step):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": step})
    response = client.get(url)

    assert response.status_code == 200


def test_cfp_editor_step_invalid(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "nonexistent"}
    )
    response = client.get(url)

    assert response.status_code == 200
    assert b"Step not found" in response.content


def test_cfp_editor_add_field(client):
    event = EventFactory(cfp__fields={"duration": {"visibility": "do_not_ask"}})
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    response = client.post(url, {"field": "duration"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["duration"]["visibility"] == "optional"


def test_cfp_editor_remove_field(client):
    event = EventFactory(cfp__fields={"duration": {"visibility": "optional"}})
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "remove"},
    )
    response = client.post(url, {"field": "duration"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["duration"]["visibility"] == "do_not_ask"


def test_cfp_editor_toggle_missing_field_returns_400(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    response = client.post(url, {})

    assert response.status_code == 400
    assert b"No field provided" in response.content


def test_cfp_editor_toggle_invalid_action_returns_400(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "invalid"},
    )
    response = client.post(url, {"field": "duration"})

    assert response.status_code == 400
    assert b"Invalid action" in response.content


def test_cfp_editor_profile_name_field_always_included(client, event):
    """The name field should always be included in the profile step."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "profile", "action": "add"},
    )
    response = client.post(url, {"field": "name"})
    assert response.status_code == 200

    step_url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "profile"}
    )
    response = client.get(step_url)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'dragsort-id="name"' in content
    name_pos = content.find('dragsort-id="name"')
    biography_pos = content.find('dragsort-id="biography"')
    assert name_pos < biography_pos


def test_cfp_editor_add_question(client, event):
    with scopes_disabled():
        question = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant="text", active=False
        )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "questions", "action": "add"},
    )
    response = client.post(url, {"field": f"question_{question.pk}"})

    assert response.status_code == 200
    with scopes_disabled():
        question = Question.all_objects.get(pk=question.pk)
        assert question.active is True


def test_cfp_editor_remove_question(client, event):
    with scopes_disabled():
        question = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant="text", active=True
        )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "questions", "action": "remove"},
    )
    response = client.post(url, {"field": f"question_{question.pk}"})

    assert response.status_code == 200
    with scopes_disabled():
        question = Question.all_objects.get(pk=question.pk)
        assert question.active is False


def test_cfp_editor_reorder_fields(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder", kwargs={"event": event.slug, "step": "info"}
    )
    response = client.post(url, {"order": "abstract,title,description"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        fields = step_config.get("fields", [])
        field_keys = [f.get("key") for f in fields]
        assert field_keys[:3] == ["abstract", "title", "description"]


def test_cfp_editor_reorder_no_order_returns_400(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder", kwargs={"event": event.slug, "step": "info"}
    )
    response = client.post(url, {})

    assert response.status_code == 400
    assert b"No order provided" in response.content


def test_cfp_editor_reorder_questions(client, event):
    with scopes_disabled():
        q1 = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant="text", position=0
        )
        q2 = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant="text", position=1
        )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = client.post(url, {"order": f"question_{q2.pk},question_{q1.pk}"})

    assert response.status_code == 200
    with scopes_disabled():
        q1.refresh_from_db()
        q2.refresh_from_db()
        assert q2.position == 0
        assert q1.position == 1


def test_cfp_editor_reorder_invalid_question_id(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = client.post(url, {"order": "question_invalid,question_abc"})

    assert response.status_code == 200
    assert b"success" in response.content


def test_cfp_editor_field_modal_get(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "abstract"},
    )
    response = client.get(url)

    assert response.status_code == 200


def test_cfp_editor_field_modal_post(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "abstract"},
    )
    response = client.post(
        url, {"visibility": "required", "min_length": "50", "max_length": "500"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["abstract"]["visibility"] == "required"
        assert event.cfp.fields["abstract"]["min_length"] == 50
        assert event.cfp.fields["abstract"]["max_length"] == 500


def test_cfp_editor_field_modal_invalid_field_returns_404(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "nonexistent_field"},
    )
    response = client.get(url)

    assert response.status_code == 404


def test_cfp_editor_field_modal_multilingual(client):
    """Field modal shows label inputs for multilingual events."""
    event = EventFactory(locale_array="en,de")
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "abstract"},
    )
    response = client.get(url)

    assert response.status_code == 200
    assert b"label" in response.content.lower()


def test_cfp_editor_tags_field_modal(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "tags"},
    )
    response = client.post(
        url, {"visibility": "optional", "min_number": "1", "max_number": "5"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["tags"]["visibility"] == "optional"
        assert event.cfp.fields["tags"]["min"] == 1
        assert event.cfp.fields["tags"]["max"] == 5


def test_cfp_editor_tags_field_modal_min_greater_than_max(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "tags"},
    )
    response = client.post(
        url, {"visibility": "optional", "min_number": "5", "max_number": "2"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        reloaded_event = Event.objects.get(slug=event.slug)
        assert reloaded_event.cfp.fields["tags"].get("min") != 5


def test_cfp_editor_question_modal(client, event):
    with scopes_disabled():
        question = QuestionFactory(event=event, question="Test Question")
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.question",
        kwargs={"event": event.slug, "question_id": question.pk},
    )
    response = client.get(url)

    assert response.status_code == 200
    assert b"Test Question" in response.content


def test_cfp_editor_question_modal_nonexistent_returns_404(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.question", kwargs={"event": event.slug, "question_id": 99999}
    )
    response = client.get(url)

    assert response.status_code == 404


def test_cfp_editor_step_header_edit(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = client.get(url + "?edit_header=1")
    assert response.status_code == 200

    response = client.post(url, {"title_0": "Custom Title", "text_0": "Custom text"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        title = step_config.get("title")
        text = step_config.get("text")
        assert title.get("en") == "Custom Title"
        assert text.get("en") == "Custom text"


def test_cfp_editor_step_header_clear_custom(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})

    client.post(url, {"title_0": "Custom Title", "text_0": "Custom text"})
    response = client.post(url, {"title_0": "", "text_0": ""})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        title = step_config.get("title")
        assert not any(title.values()) or title.get("en") == ""


def test_cfp_editor_tags_auto_hidden_without_public_tags(client):
    event = EventFactory(cfp__fields={"tags": {"visibility": "optional"}})
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = client.get(url)

    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"no public tags exist" in response.content


def test_cfp_editor_track_auto_hidden_without_tracks(client):
    event = EventFactory(
        feature_flags={"use_tracks": True},
        cfp__fields={"track": {"visibility": "optional"}},
    )
    with scopes_disabled():
        event.tracks.all().delete()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = client.get(url)

    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"no tracks exist" in response.content


def test_cfp_editor_track_auto_hidden_when_disabled(client):
    event = EventFactory(
        feature_flags={"use_tracks": False},
        cfp__fields={"track": {"visibility": "optional"}},
    )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = client.get(url)

    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"tracks are disabled" in response.content


def test_cfp_editor_reset(client):
    event = EventFactory(
        cfp__fields={"abstract": {"visibility": "required", "min_length": 50}}
    )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse("orga:cfp.editor.reset", kwargs={"event": event.slug})
    response = client.post(url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        assert not flow_config.get("steps")


def test_cfp_text_post_without_changes_no_log(client, event):
    """Submitting the CfP text form twice with the same data only logs once."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = {
        "headline_0": "stable headline",
        "text_0": "",
        "deadline": "",
        "count_length_in": "chars",
    }

    client.post(event.cfp.urls.edit_text, data, follow=True)
    with scopes_disabled():
        log_count = event.cfp.logged_actions().count()

    response = client.post(event.cfp.urls.edit_text, data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.cfp.logged_actions().count() == log_count


def test_question_update_with_next_url_redirects(client, event, question):
    """When a next URL parameter is present, the redirect goes there."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    response = client.post(
        question.urls.edit + f"?next={event.cfp.urls.questions}",
        {
            "target": "submission",
            "question_0": str(question.question),
            "variant": question.variant,
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
    )

    assert response.status_code == 302
    assert response.url == event.cfp.urls.questions


def test_question_edit_choice_options_reorder(client, event, choice_question):
    """Reordering answer options via the order POST parameter updates positions."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        options = list(choice_question.options.order_by("pk"))
        assert len(options) == 3

    response = client.post(
        choice_question.urls.base,
        {"order": f"{options[2].pk},{options[0].pk},{options[1].pk}"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        options[0].refresh_from_db()
        options[1].refresh_from_db()
        options[2].refresh_from_db()
    assert options[2].position == 0
    assert options[0].position == 1
    assert options[1].position == 2


def test_question_edit_choice_with_options_and_file_conflict(
    client, event, choice_question
):
    """Uploading an options file while also changing formset options is rejected."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    options_file = SimpleUploadedFile("opts.txt", b"Option A\nOption B")
    with scopes_disabled():
        first_option = choice_question.options.first()

    response = client.post(
        choice_question.urls.edit,
        {
            "target": "speaker",
            "question_0": str(choice_question.question),
            "variant": "choices",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
            "options": options_file,
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-id": first_option.pk,
            "form-0-answer_0": "Changed Option",
        },
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "cannot change the options and upload" in content


def test_question_edit_choice_with_invalid_formset_stays_on_page(
    client, event, choice_question
):
    """An invalid formset on a choice question keeps the user on the edit page."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        first_option = choice_question.options.first()

    response = client.post(
        choice_question.urls.edit,
        {
            "target": "speaker",
            "question_0": str(choice_question.question),
            "variant": "choices",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-id": first_option.pk,
            "form-0-answer_0": "",
        },
        follow=True,
    )

    assert response.status_code == 200


def test_question_edit_choice_unchanged_option_in_formset(
    client, event, choice_question
):
    """An unchanged initial form in the formset doesn't cause issues."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)
    with scopes_disabled():
        options = list(choice_question.options.order_by("pk"))

    response = client.post(
        choice_question.urls.edit,
        {
            "target": "speaker",
            "question_0": "Changed question text",
            "variant": "choices",
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 3,
            "form-0-id": options[0].pk,
            "form-0-answer_0": str(options[0].answer),
            "form-1-id": options[1].pk,
            "form-1-answer_0": str(options[1].answer),
            "form-2-id": options[2].pk,
            "form-2-answer_0": str(options[2].answer),
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        choice_question.refresh_from_db()
        assert str(choice_question.question) == "Changed question text"
        assert choice_question.options.count() == 3


def test_cfp_editor_step_header_edit_invalid_step(client, event):
    """Getting the step header edit form for a non-existent step returns 200
    without crashing, even though the error is not visible in the step-header-edit template."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "nonexistent"}
    )
    response = client.get(url + "?edit_header=1")

    assert response.status_code == 200
    assert response.context["error"] == "Step not found"


def test_cfp_editor_reorder_question_nonexistent_id(client, event):
    """Reordering with a valid integer question ID that doesn't exist is ignored."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = client.post(url, {"order": "question_99999"})

    assert response.status_code == 200
    assert b"success" in response.content


def test_cfp_editor_reorder_question_with_non_question_keys(client, event):
    """Non-question keys mixed into a question step reorder are safely skipped."""
    with scopes_disabled():
        q = QuestionFactory(
            event=event, target=QuestionTarget.SUBMISSION, variant="text", position=0
        )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = client.post(url, {"order": f"not_a_question,question_{q.pk}"})

    assert response.status_code == 200
    with scopes_disabled():
        q.refresh_from_db()
        assert q.position == 1


def test_cfp_editor_toggle_nonexistent_question_returns_404(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "questions", "action": "add"},
    )
    response = client.post(url, {"field": "question_99999"})

    assert response.status_code == 404
    assert b"Question not found" in response.content


def test_cfp_editor_toggle_invalid_field_key_returns_400(client, event):
    """Toggling a field key that isn't a question and isn't in default_fields returns 400."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    response = client.post(url, {"field": "totally_nonexistent_field"})

    assert response.status_code == 400
    assert b"Invalid field key" in response.content


def test_cfp_editor_toggle_field_not_in_cfp_fields_initializes(client, event):
    """Toggling a valid field that isn't yet in cfp.fields initializes it."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scopes_disabled():
        cfp = event.cfp
        cfp.fields.pop("resources", None)
        cfp.save()

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    response = client.post(url, {"field": "resources"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["resources"]["visibility"] == "optional"


def test_cfp_editor_field_modal_post_field_not_in_cfp_fields(client, event):
    """Posting field config for a field not yet in cfp.fields initializes it."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scopes_disabled():
        cfp = event.cfp
        cfp.fields.pop("description", None)
        cfp.save()

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "description"},
    )
    response = client.post(
        url, {"visibility": "optional", "min_length": "10", "max_length": "200"}
    )

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["description"]["visibility"] == "optional"
        assert event.cfp.fields["description"]["min_length"] == 10


def test_cfp_editor_additional_speaker_field_max(client, event):
    """The additional_speaker field has a max field that limits speaker count."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "additional_speaker"},
    )
    response = client.post(url, {"visibility": "optional", "max": "5"})

    assert response.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["additional_speaker"]["max"] == 5


def test_cfp_editor_field_modal_with_custom_label(client, event):
    """Setting a custom label via the flow editor and then viewing the step
    applies the label to the preview form field."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    field_url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "abstract"},
    )
    response = client.post(
        field_url,
        {
            "visibility": "required",
            "min_length": "",
            "max_length": "",
            "label_0": "Custom Abstract Label",
            "help_text_0": "Custom help text here",
        },
    )
    assert response.status_code == 200

    step_url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"}
    )
    response = client.get(step_url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Custom Abstract Label" in content


def test_question_detail_with_all_base_search_url_filters(
    client, event, question, track, submission_type
):
    """The question detail view builds correct base_search_url with all filter params."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    url = (
        question.urls.base
        + f"?role=accepted&track={track.pk}&submission_type={submission_type.pk}"
    )
    response = client.get(url, follow=True)

    assert response.status_code == 200


def test_question_update_without_view_permission_redirects_to_list(client, event):
    """A user with edit but not view permission is redirected to the list after saving."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=False
    )
    client.force_login(user)
    with scopes_disabled():
        question = QuestionFactory(event=event)

    list_url = reverse("orga:cfp.questions.list", kwargs={"event": event.slug})

    response = client.post(
        question.urls.edit,
        {
            "target": "submission",
            "question_0": str(question.question),
            "variant": question.variant,
            "active": True,
            "help_text_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.url == list_url


def test_question_detail_post_without_order_returns_400(client, event, question):
    """POSTing to the question detail URL without an order param returns 400."""
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    client.force_login(user)

    url = reverse(
        "orga:cfp.questions.detail", kwargs={"event": event.slug, "pk": question.pk}
    )
    response = client.post(url, {})

    assert response.status_code == 400
