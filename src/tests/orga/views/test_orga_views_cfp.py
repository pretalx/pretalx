# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Johan Van de Wauw
# SPDX-FileContributor: Natalia Katsiapi

import datetime as dt
from io import BytesIO
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pytest
from django.core import mail as djmail
from django.core.files.base import ContentFile
from django.urls import reverse
from django_scopes import scope

from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event
from pretalx.mail.models import QueuedMail
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import (
    Question,
    QuestionTarget,
    Submission,
    SubmitterAccessCode,
    Track,
)
from pretalx.submission.models.question import Answer, QuestionRequired, QuestionVariant


@pytest.mark.django_db
def test_edit_cfp(orga_client, event):
    response = orga_client.post(
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
    assert response.status_code == 200


@pytest.mark.django_db
def test_edit_cfp_timezones(orga_client, event):
    event = Event.objects.get(slug=event.slug)
    event.timezone = "Europe/Berlin"
    event.save()
    event.cfp.deadline = dt.datetime(2018, 3, 5, 17, 39, 15, tzinfo=ZoneInfo("UTC"))
    event.cfp.save()
    response = orga_client.get(event.cfp.urls.edit_text)
    assert response.status_code == 200
    assert "2018-03-05T18:39" in response.rendered_content
    assert "2018-03-05T17:39" not in response.rendered_content


@pytest.mark.django_db
def test_edit_cfp_flow_shows_in_frontend(orga_client, event):
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = orga_client.post(
        url,
        {"title_0": "TEST CFP WOO", "text_0": "PLS SUBMIT HERE THX"},
    )
    assert response.status_code == 200, response.text

    response = orga_client.get(event.cfp.urls.submit, follow=True)
    assert response.status_code == 200
    assert "TEST CFP WOO" in response.text
    assert "PLS SUBMIT HERE THX" in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("step", ("info", "questions", "user", "profile"))
def test_cfp_editor_step_view(orga_client, event, step):
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": step})
    response = orga_client.get(url)
    assert response.status_code == 200
    assert (
        f'id="step-{step}"'.encode() in response.content
        or f"id=step-{step}".encode() in response.content
    )


@pytest.mark.django_db
def test_cfp_editor_add_field(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        event.cfp.fields["duration"] = {"visibility": "do_not_ask"}
        event.cfp.save()

    response = orga_client.post(url, {"field": "duration"})
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["duration"]["visibility"] == "optional"


@pytest.mark.django_db
def test_cfp_editor_remove_field(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "remove"},
    )
    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        event.cfp.fields["duration"] = {"visibility": "optional"}
        event.cfp.save()

    response = orga_client.post(url, {"field": "duration"})
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["duration"]["visibility"] == "do_not_ask"


@pytest.mark.django_db
def test_cfp_editor_profile_name_field_always_included(orga_client, event):
    """The name field should always be included in the profile step."""
    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "profile", "action": "add"},
    )
    response = orga_client.post(url, {"field": "name"})
    assert response.status_code == 200

    step_url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "profile"}
    )
    response = orga_client.get(step_url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "dragsort-id=name" in content
    # It should appear before other fields by default
    name_pos = content.find("dragsort-id=name")
    biography_pos = content.find("dragsort-id=biography")
    assert name_pos < biography_pos, "Name field should appear before biography"


@pytest.mark.django_db
def test_cfp_editor_reorder_fields(orga_client, event):
    url = reverse(
        "orga:cfp.editor.reorder", kwargs={"event": event.slug, "step": "info"}
    )
    response = orga_client.post(url, {"order": "abstract,title,description"})
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        fields = step_config.get("fields", [])
        field_keys = [f.get("key") for f in fields]
        assert field_keys[:3] == ["abstract", "title", "description"]


@pytest.mark.django_db
def test_cfp_editor_field_modal(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "abstract"},
    )

    response = orga_client.get(url)
    assert response.status_code == 200

    response = orga_client.post(
        url, {"visibility": "required", "min_length": "50", "max_length": "500"}
    )
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["abstract"]["visibility"] == "required"
        assert event.cfp.fields["abstract"]["min_length"] == 50
        assert event.cfp.fields["abstract"]["max_length"] == 500


@pytest.mark.django_db
def test_cfp_editor_field_modal_multilingual(orga_client, multilingual_event):
    url = reverse(
        "orga:cfp.editor.field",
        kwargs={
            "event": multilingual_event.slug,
            "step": "info",
            "field_key": "abstract",
        },
    )

    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"label" in response.content.lower()


@pytest.mark.django_db
def test_cfp_editor_tags_field_modal(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "tags"},
    )

    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"public tags" in response.content.lower()
    assert b"min_number" in response.content
    assert b"max_number" in response.content

    response = orga_client.post(
        url, {"visibility": "optional", "min_number": "1", "max_number": "5"}
    )
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        assert event.cfp.fields["tags"]["visibility"] == "optional"
        assert event.cfp.fields["tags"]["min"] == 1
        assert event.cfp.fields["tags"]["max"] == 5


@pytest.mark.django_db
def test_cfp_editor_tags_field_modal_min_greater_than_max(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field",
        kwargs={"event": event.slug, "step": "info", "field_key": "tags"},
    )

    response = orga_client.post(
        url, {"visibility": "optional", "min_number": "5", "max_number": "2"}
    )
    assert response.status_code == 200
    content_lower = response.content.decode().lower()
    assert "cannot be greater than" in content_lower or "minimum" in content_lower

    with scope(event=event):
        reloaded_event = Event.objects.get(slug=event.slug)
        assert reloaded_event.cfp.fields["tags"].get("min") != 5


@pytest.mark.django_db
def test_cfp_editor_add_question(orga_client, event):
    with scope(event=event):
        question = Question.objects.create(
            event=event,
            question="Test Question",
            target=QuestionTarget.SUBMISSION,
            variant="text",
            active=False,
        )
        question_id = question.pk

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "questions", "action": "add"},
    )
    response = orga_client.post(url, {"field": f"question_{question_id}"})
    assert response.status_code == 200

    with scope(event=event):
        question = Question.all_objects.get(pk=question_id)
        assert question.active is True


@pytest.mark.django_db
def test_cfp_editor_remove_question(orga_client, event):
    with scope(event=event):
        question = Question.objects.create(
            event=event,
            question="Test Question",
            target=QuestionTarget.SUBMISSION,
            variant="text",
            active=True,
        )
        question_id = question.pk

    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "questions", "action": "remove"},
    )
    response = orga_client.post(url, {"field": f"question_{question_id}"})
    assert response.status_code == 200

    with scope(event=event):
        question = Question.all_objects.get(pk=question_id)
        assert question.active is False


@pytest.mark.django_db
def test_cfp_editor_question_modal(orga_client, event):
    with scope(event=event):
        question = Question.objects.create(
            event=event,
            question="Test Question",
            target=QuestionTarget.SUBMISSION,
            variant="text",
            active=True,
        )
        question_id = question.pk

    url = reverse(
        "orga:cfp.editor.question",
        kwargs={"event": event.slug, "question_id": question_id},
    )
    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"Test Question" in response.content


@pytest.mark.django_db
def test_cfp_editor_reorder_questions(orga_client, event):
    with scope(event=event):
        q1 = Question.objects.create(
            event=event,
            question="Question 1",
            target=QuestionTarget.SUBMISSION,
            variant="text",
            active=True,
            position=0,
        )
        q2 = Question.objects.create(
            event=event,
            question="Question 2",
            target=QuestionTarget.SUBMISSION,
            variant="text",
            active=True,
            position=1,
        )

    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = orga_client.post(url, {"order": f"question_{q2.pk},question_{q1.pk}"})
    assert response.status_code == 200

    with scope(event=event):
        q1.refresh_from_db()
        q2.refresh_from_db()
        assert q2.position == 0
        assert q1.position == 1


@pytest.mark.django_db
def test_cfp_editor_step_header_edit(orga_client, event):
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = orga_client.get(url + "?edit_header=1")
    assert response.status_code == 200
    assert b"Edit Step" in response.content
    assert b"id_title" in response.content
    assert b"id_text" in response.content

    response = orga_client.post(
        url,
        {
            "title_0": "Custom Title",
            "text_0": "Custom text",
        },
    )
    assert response.status_code == 200

    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        title = step_config.get("title")
        text = step_config.get("text")
        assert title.get("en") == "Custom Title"
        assert text.get("en") == "Custom text"


@pytest.mark.django_db
def test_make_submission_type_default(
    orga_client, submission_type, default_submission_type
):
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2
        assert submission_type.event.cfp.default_type == default_submission_type
    response = orga_client.get(submission_type.urls.default, follow=True)
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2
        submission_type.event.cfp.refresh_from_db()
        assert submission_type.event.cfp.default_type == submission_type


@pytest.mark.django_db
def test_edit_submission_type(orga_client, submission_type):
    with scope(event=submission_type.event):
        count = submission_type.logged_actions().count()
    response = orga_client.post(
        submission_type.urls.edit,
        {"default_duration": 31, "slug": "New_Type", "name_0": "New Type!"},
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert count + 1 == submission_type.logged_actions().count()
        submission_type.refresh_from_db()
    assert submission_type.default_duration == 31
    assert str(submission_type.name) == "New Type!"


@pytest.mark.django_db
def test_edit_submission_type_without_change(orga_client, submission_type):
    with scope(event=submission_type.event):
        count = submission_type.logged_actions().count()
    response = orga_client.post(
        submission_type.urls.edit,
        {
            "default_duration": submission_type.default_duration,
            "slug": submission_type.slug,
            "name_0": str(submission_type.name),
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert count == submission_type.logged_actions().count()


@pytest.mark.django_db
def test_delete_submission_type(orga_client, submission_type, default_submission_type):
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2
    response = orga_client.get(submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2
    response = orga_client.post(submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 1


@pytest.mark.django_db
def test_delete_used_submission_type(
    orga_client, event, submission_type, default_submission_type, submission
):
    with scope(event=event):
        assert submission_type.event.submission_types.count() == 2
        submission.submission_type = submission_type
        submission.save()
    response = orga_client.post(submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert submission_type.event.submission_types.count() == 2


@pytest.mark.django_db
def test_delete_last_submission_type(orga_client, event):
    submission_type = event.cfp.default_type
    with scope(event=event):
        assert submission_type.event.submission_types.count() == 1
    response = orga_client.post(submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert submission_type.event.submission_types.count() == 1


@pytest.mark.django_db
def test_delete_default_submission_type(
    orga_client, submission_type, default_submission_type
):
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2
    response = orga_client.post(default_submission_type.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=submission_type.event):
        assert default_submission_type.event.submission_types.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_all_questions_in_list(
    orga_client,
    question,
    inactive_question,
    event,
    django_assert_num_queries,
    item_count,
):
    if item_count != 2:
        with scope(event=event):
            inactive_question.delete()

    with django_assert_num_queries(23):
        response = orga_client.get(event.cfp.urls.questions, follow=True)
    assert response.status_code == 200
    assert question.question in response.text
    if item_count == 2:
        assert inactive_question.question in response.text


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_submission_type_list_num_queries(
    orga_client,
    event,
    submission_type,
    default_submission_type,
    django_assert_num_queries,
    item_count,
):
    if item_count != 2:
        with scope(event=event):
            submission_type.delete()

    with django_assert_num_queries(21):
        response = orga_client.get(event.cfp.urls.types)
    assert response.status_code == 200
    assert str(default_submission_type.name) in response.text


@pytest.mark.django_db
def test_delete_question(orga_client, event, question):
    with scope(event=event):
        assert event.questions.count() == 1
    response = orga_client.get(question.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.questions.count() == 1
    response = orga_client.post(question.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.questions.count() == 0
        assert Question.all_objects.filter(event=event).count() == 0


@pytest.mark.django_db
def test_delete_inactive_question(orga_client, event, inactive_question):
    with scope(event=event):
        assert Question.all_objects.filter(event=event).count() == 1
    response = orga_client.post(inactive_question.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.questions.count() == 0
        assert Question.all_objects.filter(event=event).count() == 0


@pytest.mark.django_db
def test_delete_choice_question(orga_client, event, choice_question):
    with scope(event=event):
        assert Question.all_objects.filter(event=event).count() == 1
    response = orga_client.post(choice_question.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.questions.count() == 0
        assert Question.all_objects.filter(event=event).count() == 0


@pytest.mark.django_db
def test_cannot_delete_answered_question(orga_client, event, answered_choice_question):
    with scope(event=event):
        assert event.questions.count() == 1
        assert answered_choice_question.answers.count() == 1
        assert answered_choice_question.options.count() == 3
    response = orga_client.post(answered_choice_question.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        answered_choice_question = Question.all_objects.get(
            pk=answered_choice_question.pk
        )
        assert answered_choice_question
        assert not answered_choice_question.active
        assert event.questions.count() == 0
        assert answered_choice_question.answers.count() == 1
        assert answered_choice_question.options.count() == 3


@pytest.mark.django_db
def test_can_add_simple_question(orga_client, event):
    with scope(event=event):
        assert event.questions.count() == 0
    response = orga_client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 1
        q = event.questions.first()
        assert str(q.question) == "What is your name?"
        assert q.variant == "string"
    response = orga_client.get(q.urls.base + "?role=true", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text
    response = orga_client.get(q.urls.base + "?role=false", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text


@pytest.mark.django_db
def test_can_add_simple_question_required_freeze(orga_client, event):
    with scope(event=event):
        assert event.questions.count() == 0
    response = orga_client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
            "question_required": QuestionRequired.REQUIRED,
            "freeze_after": "2021-06-22T12:44:42Z",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 1
        q = event.questions.first()
        assert str(q.question) == "What is your name?"
        assert q.variant == "string"
    response = orga_client.get(q.urls.base + "?role=true", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text
    response = orga_client.get(q.urls.base + "?role=false", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text


@pytest.mark.django_db
def test_can_add_simple_question_after_deadline(orga_client, event):
    with scope(event=event):
        assert event.questions.count() == 0
    response = orga_client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
            "question_required": QuestionRequired.AFTER_DEADLINE,
            "deadline": "2021-06-22T12:44:42Z",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 1
        q = event.questions.first()
        assert str(q.question) == "What is your name?"
        assert q.variant == "string"
        assert q.deadline == dt.datetime(
            2021, 6, 22, 12, 44, 42, tzinfo=ZoneInfo("UTC")
        )
    response = orga_client.get(q.urls.base + "?role=true", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text
    response = orga_client.get(q.urls.base + "?role=false", follow=True)
    with scope(event=event):
        assert str(q.question) in response.text


@pytest.mark.django_db
def test_can_add_simple_question_after_deadline_missing_deadline(orga_client, event):
    with scope(event=event):
        assert event.questions.count() == 0
    orga_client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "What is your name?",
            "variant": "string",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
            "question_required": QuestionRequired.AFTER_DEADLINE,
        },
        follow=True,
    )
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 0


@pytest.mark.django_db
def test_can_add_choice_question(orga_client, event):
    with scope(event=event):
        assert event.questions.count() == 0
    response = orga_client.post(
        event.cfp.urls.new_question,
        {
            "target": "submission",
            "question_0": "Is it an African or a European swallow?",
            "variant": "choices",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
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
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 1
        q = event.questions.first()
        assert q.variant == "choices"
        assert q.options.count() == 2


@pytest.mark.django_db
def test_can_edit_choice_question(orga_client, event, choice_question):
    with scope(event=event):
        count = choice_question.options.count()
        assert str(choice_question.options.first().answer) != "African"
        first_option = choice_question.options.first().pk
        last_option = choice_question.options.last().pk
        other_option = choice_question.options.all()[1]
        other_answer = str(other_option.answer)
    response = orga_client.post(
        choice_question.urls.edit,
        {
            "target": "submission",
            "question_0": "Is it an African or a European swallow?",
            "variant": "choices",
            "active": True,
            "help_text_0": "Answer if you want to reach the other side!",
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 3,
            "form-0-id": first_option,
            "form-0-answer_0": "African",
            "form-1-id": last_option,
            "form-1-answer_0": "European",
            "form-2-id": other_option.pk,
            "form-2-answer_0": other_answer,
            "form-2-DELETE": "on",
            "form-3-id": "",
            "form-3-answer_0": "",
            "question_required": QuestionRequired.OPTIONAL,
        },
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=event):
        event.refresh_from_db()
        assert event.questions.count() == 1
        assert choice_question.variant == "choices"
        assert choice_question.options.count() == count - 1
        assert str(choice_question.options.first().answer) == "African"


@pytest.mark.parametrize(
    ("role", "count"), (("accepted", 1), ("confirmed", 1), ("", 2))
)
@pytest.mark.django_db
def test_can_remind_speaker_question(
    orga_client,
    event,
    speaker_question,
    review_question,
    speaker,
    slot,
    other_speaker,
    other_submission,
    role,
    count,
):
    with scope(event=event):
        original_count = QueuedMail.objects.count()
    response = orga_client.post(
        event.cfp.urls.remind_questions, {"role": role}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert QueuedMail.objects.count() == original_count + count


@pytest.mark.parametrize(
    ("role", "count"), (("accepted", 1), ("confirmed", 1), ("", 2))
)
@pytest.mark.django_db
def test_can_remind_submission_question(
    orga_client,
    event,
    question,
    speaker,
    slot,
    other_speaker,
    other_submission,
    role,
    count,
):
    with scope(event=event):
        original_count = QueuedMail.objects.count()
    response = orga_client.post(
        event.cfp.urls.remind_questions, {"role": role}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert QueuedMail.objects.count() == original_count + count


@pytest.mark.parametrize(
    ("role", "count"), (("accepted", 1), ("confirmed", 1), ("", 2))
)
@pytest.mark.django_db
def test_can_remind_multiple_questions(
    orga_client,
    event,
    question,
    speaker_question,
    speaker,
    slot,
    other_speaker,
    other_submission,
    role,
    count,
):
    with scope(event=event):
        original_count = QueuedMail.objects.count()
    response = orga_client.post(
        event.cfp.urls.remind_questions, {"role": role}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert QueuedMail.objects.count() == original_count + count


@pytest.mark.django_db
def test_can_remind_submission_question_broken_filter(
    orga_client,
    event,
):
    response = orga_client.post(
        event.cfp.urls.remind_questions, {"role": "hahaha"}, follow=True
    )
    assert response.status_code == 200
    assert "Could not send mails" in response.text


@pytest.mark.parametrize(
    ("role", "count"), (("accepted", 0), ("confirmed", 0), ("", 0))
)
@pytest.mark.django_db
def test_can_remind_answered_submission_question(
    orga_client,
    event,
    question,
    speaker,
    slot,
    other_speaker,
    other_submission,
    role,
    count,
):
    with scope(event=event):
        question.question_required = QuestionRequired.REQUIRED
        question.deadline = None
        question.save()
        original_count = QueuedMail.objects.count()
        Answer.objects.create(
            submission=slot.submission,
            question=question,
            answer="something",
        )
        Answer.objects.create(
            submission=other_submission,
            question=question,
            answer="something",
        )
    response = orga_client.post(
        event.cfp.urls.remind_questions, {"role": role}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert QueuedMail.objects.count() == original_count + count


@pytest.mark.django_db
def test_can_hide_question(orga_client, question):
    assert question.active

    response = orga_client.get(question.urls.toggle, follow=True)
    with scope(event=question.event):
        question = Question.all_objects.get(pk=question.pk)

    assert response.status_code == 200
    assert not question.active


@pytest.mark.django_db
def test_can_activate_inactive_question(orga_client, inactive_question):
    assert not inactive_question.active

    response = orga_client.get(inactive_question.urls.toggle, follow=True)
    inactive_question.refresh_from_db()

    assert response.status_code == 200
    assert inactive_question.active


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_can_see_tracks(
    orga_client, track, event, django_assert_num_queries, item_count
):
    if item_count == 2:
        with scope(event=event):
            Track.objects.create(event=event, name="Other Track", color="#ff0000")

    with django_assert_num_queries(20):
        response = orga_client.get(event.cfp.urls.tracks)
    assert response.status_code == 200
    assert str(track.name) in response.text


@pytest.mark.django_db
def test_can_see_single_track(orga_client, track):
    response = orga_client.get(track.urls.base)
    assert response.status_code == 200
    assert track.name in response.text


@pytest.mark.django_db
def test_can_edit_track(orga_client, track):
    with scope(event=track.event):
        count = track.logged_actions().count()
    response = orga_client.post(
        track.urls.base, {"name_0": "Name", "color": "#ffff99"}, follow=True
    )
    assert response.status_code == 200
    with scope(event=track.event):
        assert track.logged_actions().count() == count + 1
        track.refresh_from_db()
    assert str(track.name) == "Name"


@pytest.mark.django_db
def test_can_edit_track_without_changes(orga_client, track):
    with scope(event=track.event):
        count = track.logged_actions().count()
    response = orga_client.post(
        track.urls.base, {"name_0": str(track.name), "color": track.color}, follow=True
    )
    assert response.status_code == 200
    with scope(event=track.event):
        assert track.logged_actions().count() == count


@pytest.mark.django_db
def test_cannot_set_incorrect_track_color(orga_client, track):
    response = orga_client.post(
        track.urls.base, {"name_0": "Name", "color": "#fgff99"}, follow=True
    )
    assert response.status_code == 200
    track.refresh_from_db()
    assert str(track.name) != "Name"


@pytest.mark.django_db
def test_can_delete_single_track(orga_client, track, event):
    response = orga_client.get(track.urls.delete)
    assert response.status_code == 200
    with scope(event=event):
        assert event.tracks.count() == 1
    response = orga_client.post(track.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.tracks.count() == 0


@pytest.mark.django_db
def test_cannot_delete_used_track(orga_client, track, event, submission):
    response = orga_client.get(track.urls.delete)
    assert response.status_code == 200
    with scope(event=event):
        assert event.tracks.count() == 1
        submission.track = track
        submission.save()
    response = orga_client.post(track.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.tracks.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 2))
def test_can_see_access_codes(
    orga_client, access_code, event, django_assert_num_queries, item_count
):
    if item_count == 2:
        SubmitterAccessCode.objects.create(event=event, code="OTHERCODE")

    with django_assert_num_queries(20):
        response = orga_client.get(event.cfp.urls.access_codes)
    assert response.status_code == 200
    assert access_code.code in response.text


@pytest.mark.django_db
def test_can_see_single_access_code(orga_client, access_code):
    response = orga_client.get(access_code.urls.edit)
    assert response.status_code == 200
    assert access_code.code in response.text


@pytest.mark.django_db
def test_can_create_access_code(orga_client, event):
    with scope(event=event):
        assert event.submitter_access_codes.all().count() == 0
    response = orga_client.get(event.cfp.urls.new_access_code, follow=True)
    assert response.status_code == 200
    response = orga_client.post(
        event.cfp.urls.new_access_code, {"code": "LOLCODE"}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert event.submitter_access_codes.get(code="LOLCODE")


@pytest.mark.django_db
def test_cannot_create_access_code_with_forbidden_characters(orga_client, event):
    with scope(event=event):
        assert event.submitter_access_codes.all().count() == 0
    response = orga_client.get(event.cfp.urls.new_access_code, follow=True)
    assert response.status_code == 200
    response = orga_client.post(
        event.cfp.urls.new_access_code, {"code": "LOL %CODE"}, follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert event.submitter_access_codes.all().count() == 0


@pytest.mark.django_db
def test_can_edit_access_code(orga_client, access_code):
    with scope(event=access_code.event):
        count = access_code.logged_actions().count()
    response = orga_client.post(access_code.urls.edit, {"code": "LOLCODE"}, follow=True)
    assert response.status_code == 200
    with scope(event=access_code.event):
        access_code.refresh_from_db()
        assert access_code.logged_actions().count() == count + 1
    assert access_code.code == "LOLCODE"


@pytest.mark.django_db
def test_can_edit_access_code_without_change(orga_client, access_code):
    with scope(event=access_code.event):
        count = access_code.logged_actions().count()
    response = orga_client.post(
        access_code.urls.edit,
        {"code": access_code.code, "maximum_uses": access_code.maximum_uses},
        follow=True,
    )
    assert response.status_code == 200
    with scope(event=access_code.event):
        access_code.refresh_from_db()
        assert access_code.logged_actions().count() == count


@pytest.mark.django_db
def test_can_delete_single_access_code(orga_client, access_code, event):
    response = orga_client.get(access_code.urls.delete)
    assert response.status_code == 200
    with scope(event=event):
        assert event.submitter_access_codes.count() == 1
    response = orga_client.post(access_code.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.submitter_access_codes.count() == 0


@pytest.mark.django_db
def test_cannot_delete_used_access_code(orga_client, access_code, event, submission):
    with scope(event=event):
        assert event.submitter_access_codes.count() == 1
        submission.access_code = access_code
        submission.save()
    response = orga_client.post(access_code.urls.delete, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.submitter_access_codes.count() == 1


@pytest.mark.django_db
def test_can_send_access_code(orga_client, access_code):
    djmail.outbox = []
    response = orga_client.get(access_code.urls.send, follow=True)
    assert response.status_code == 200
    response = orga_client.post(
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


@pytest.mark.django_db
def test_can_send_special_access_code(orga_client, access_code, track):
    access_code.track = track
    access_code.valid_until = access_code.event.datetime_from
    access_code.maximum_uses = 3
    access_code.save()
    djmail.outbox = []
    response = orga_client.get(access_code.urls.send, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_cfp_editor_invalid_step(orga_client, event):
    url = reverse(
        "orga:cfp.editor.step", kwargs={"event": event.slug, "step": "nonexistent"}
    )
    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"Step not found" in response.content


@pytest.mark.django_db
def test_cfp_editor_reorder_invalid_question_id(orga_client, event):
    url = reverse(
        "orga:cfp.editor.reorder",
        kwargs={"event": event.slug, "step": "questions_submission"},
    )
    response = orga_client.post(url, {"order": "question_invalid,question_abc"})
    assert response.status_code == 200
    assert b"success" in response.content


@pytest.mark.django_db
def test_cfp_editor_toggle_missing_field(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "add"},
    )
    response = orga_client.post(url, {})
    assert response.status_code == 400
    assert b"No field provided" in response.content


@pytest.mark.django_db
def test_cfp_editor_toggle_invalid_action(orga_client, event):
    url = reverse(
        "orga:cfp.editor.field_toggle",
        kwargs={"event": event.slug, "step": "info", "action": "invalid"},
    )
    response = orga_client.post(url, {"field": "duration"})
    assert response.status_code == 400
    assert b"Invalid action" in response.content


@pytest.mark.django_db
def test_cfp_editor_reorder_no_order(orga_client, event):
    url = reverse(
        "orga:cfp.editor.reorder", kwargs={"event": event.slug, "step": "info"}
    )
    response = orga_client.post(url, {})
    assert response.status_code == 400
    assert b"No order provided" in response.content


@pytest.mark.django_db
def test_cfp_editor_step_header_clear_custom(orga_client, event):
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    orga_client.post(url, {"title_0": "Custom Title", "text_0": "Custom text"})
    response = orga_client.post(url, {"title_0": "", "text_0": ""})
    assert response.status_code == 200
    with scope(event=event):
        event = Event.objects.get(slug=event.slug)
        flow_config = event.cfp.settings.get("flow", {})
        step_config = flow_config.get("steps", {}).get("info", {})
        title = step_config.get("title")
        assert not any(title.values()) or title.get("en") == ""


@pytest.mark.django_db
def test_cfp_editor_main_view(orga_client, event):
    response = orga_client.get(event.cfp.urls.editor)
    assert response.status_code == 200
    assert b"submission-steps" in response.content
    assert b'id="step-info"' in response.content or b"id=step-info" in response.content


@pytest.mark.django_db
def test_cfp_editor_question_modal_nonexistent(orga_client, event):
    url = reverse(
        "orga:cfp.editor.question",
        kwargs={"event": event.slug, "question_id": 99999},
    )
    response = orga_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_cfp_editor_tags_auto_hidden_without_public_tags(orga_client, event):
    with scope(event=event):
        event.cfp.fields["tags"] = {"visibility": "optional"}
        event.cfp.save()
        assert event.tags.filter(is_public=True).count() == 0
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"no public tags exist" in response.content


@pytest.mark.django_db
def test_cfp_editor_track_auto_hidden_without_tracks(orga_client, event):
    with scope(event=event):
        event.feature_flags["use_tracks"] = True
        event.save()
        event.cfp.fields["track"] = {"visibility": "optional"}
        event.cfp.save()
        event.tracks.all().delete()
        assert event.tracks.count() == 0
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"no tracks exist" in response.content


@pytest.mark.django_db
def test_cfp_editor_track_auto_hidden_when_disabled(orga_client, event):
    with scope(event=event):
        event.feature_flags["use_tracks"] = False
        event.save()
        event.cfp.fields["track"] = {"visibility": "optional"}
        event.cfp.save()
    url = reverse("orga:cfp.editor.step", kwargs={"event": event.slug, "step": "info"})
    response = orga_client.get(url)
    assert response.status_code == 200
    assert b"Currently hidden" in response.content
    assert b"tracks are disabled" in response.content


@pytest.mark.django_db
def test_question_file_download_non_file_question(orga_client, question):
    response = orga_client.get(question.urls.download, follow=True)
    assert response.status_code == 200
    assert "does not support file downloads" in response.text


@pytest.mark.django_db
def test_question_file_download_permission_denied(client, file_question):
    response = client.get(file_question.urls.download)
    assert response.status_code == 302


@pytest.mark.django_db
def test_question_file_download_creates_cached_file(
    orga_client, event, file_question, submission, speaker
):
    with scope(event=event):
        answer = Answer.objects.create(
            submission=submission,
            question=file_question,
            answer="doc.pdf",
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"pdf content"))
        answer.save()

    initial_count = CachedFile.objects.count()
    response = orga_client.get(file_question.urls.download, follow=False)
    # In eager mode (tests), task runs synchronously, so we get a 200 response directly
    assert response.status_code == 200
    assert CachedFile.objects.count() == initial_count + 1


@pytest.mark.django_db
def test_question_file_download_generates_zip(
    orga_client, event, file_question, submission, speaker
):
    with scope(event=event):
        answer = Answer.objects.create(
            submission=submission,
            question=file_question,
            answer="test.txt",
        )
        answer.answer_file.save("test.txt", ContentFile(b"test content"))
        answer.save()

    response = orga_client.get(file_question.urls.download)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"

    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert submission.code in names[0]
        assert zf.read(names[0]) == b"test content"


@pytest.mark.django_db
def test_question_file_download_duplicate_filenames(
    orga_client, event, submission, speaker
):
    with scope(event=event):
        file_question = Question.objects.create(
            event=event,
            question="Upload file",
            variant=QuestionVariant.FILE,
            target="submission",
        )
        other_submission = Submission.objects.create(
            event=event,
            title="Other submission",
            submission_type=event.cfp.default_type,
        )
        speaker_profile = SpeakerProfile.objects.get(user=speaker, event=event)
        other_submission.speakers.add(speaker_profile)
        answer1 = Answer.objects.create(
            submission=submission,
            question=file_question,
            answer="same.txt",
        )
        answer1.answer_file.save("same.txt", ContentFile(b"content 1"))
        answer1.save()

        answer2 = Answer.objects.create(
            submission=other_submission,
            question=file_question,
            answer="same.txt",
        )
        answer2.answer_file.save("same.txt", ContentFile(b"content 2"))
        answer2.save()

    response = orga_client.get(file_question.urls.download)
    assert response.status_code == 200

    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        contents = {zf.read(name) for name in names}
        assert contents == {b"content 1", b"content 2"}


@pytest.mark.django_db
def test_question_file_download_speaker_question(
    orga_client, event, speaker_file_question, speaker_profile
):
    with scope(event=event):
        answer = Answer.objects.create(
            question=speaker_file_question,
            speaker=speaker_profile,
            answer="cv.pdf",
        )
        answer.answer_file.save("cv.pdf", ContentFile(b"CV content"))
        answer.save()

    response = orga_client.get(speaker_file_question.urls.download)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"

    zip_content = b"".join(response.streaming_content)
    with ZipFile(BytesIO(zip_content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert speaker_profile.code in names[0]
        assert zf.read(names[0]) == b"CV content"
