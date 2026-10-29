# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.submission.models import Answer, AnswerOption, Question
from pretalx.submission.models.question import (
    QuestionIcon,
    QuestionRequired,
    QuestionTarget,
    QuestionVariant,
    answer_file_path,
)
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_question_manager_excludes_inactive_and_reviewer_questions():
    event = EventFactory()
    inactive_q = QuestionFactory(event=event, active=False, position=1)
    active_q = QuestionFactory(event=event, active=True, position=0)
    reviewer_q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, position=2
    )

    assert list(Question.objects.filter(event=event)) == [active_q]
    assert set(Question.all_objects.filter(event=event)) == {
        active_q,
        inactive_q,
        reviewer_q,
    }
    assert list(Question.get_order_queryset(event)) == [
        active_q,
        inactive_q,
        reviewer_q,
    ]


def test_question_str_and_log_parent():
    question = QuestionFactory(question="What is your T-shirt size?")

    assert str(question) == "What is your T-shirt size?"
    assert question.log_parent == question.event


@pytest.mark.parametrize(
    ("question_required", "deadline_delta", "freeze_delta", "expected"),
    (
        (QuestionRequired.OPTIONAL, None, None, False),
        (QuestionRequired.REQUIRED, None, None, True),
        (QuestionRequired.AFTER_DEADLINE, timedelta(days=1), None, False),
        (QuestionRequired.AFTER_DEADLINE, timedelta(days=-1), None, True),
        (QuestionRequired.REQUIRED, None, timedelta(days=-1), False),
        (QuestionRequired.REQUIRED, None, timedelta(days=1), True),
        (
            QuestionRequired.AFTER_DEADLINE,
            timedelta(days=-1),
            timedelta(hours=-1),
            False,
        ),
        (QuestionRequired.OPTIONAL, None, timedelta(days=-1), False),
    ),
    ids=(
        "optional",
        "always_required",
        "after_deadline_before",
        "after_deadline_past",
        "required_but_frozen",
        "required_not_yet_frozen",
        "after_deadline_and_frozen",
        "optional_and_frozen",
    ),
)
def test_question_required(question_required, deadline_delta, freeze_delta, expected):
    kwargs = {"question_required": question_required}
    if deadline_delta is not None:
        kwargs["deadline"] = tz_now() + deadline_delta
    if freeze_delta is not None:
        kwargs["freeze_after"] = tz_now() + freeze_delta
    question = QuestionFactory(**kwargs)
    assert question.required is expected


@pytest.mark.parametrize(
    ("freeze_delta", "expected"),
    ((timedelta(days=-1), True), (timedelta(days=1), False), (None, False)),
    ids=("past", "future", "unset"),
)
def test_question_read_only(freeze_delta, expected):
    question = QuestionFactory(
        freeze_after=tz_now() + freeze_delta if freeze_delta else None
    )
    assert bool(question.read_only) is expected


@pytest.mark.parametrize(
    ("variant", "icon", "expected"),
    (
        (QuestionVariant.URL, QuestionIcon.GITHUB, True),
        (QuestionVariant.URL, "", False),
        (QuestionVariant.URL, "-", False),
        (QuestionVariant.URL, None, False),
        (QuestionVariant.STRING, QuestionIcon.GITHUB, False),
    ),
    ids=(
        "url_with_icon",
        "url_empty_icon",
        "url_dash_icon",
        "url_none_icon",
        "non_url_variant",
    ),
)
def test_question_show_icon(variant, icon, expected):
    question = QuestionFactory(variant=variant, icon=icon)
    assert question.show_icon is expected


def test_question_icon_url_only_when_icon_shown():
    event = EventFactory()
    with_icon = QuestionFactory(
        event=event, variant=QuestionVariant.URL, icon=QuestionIcon.GITHUB
    )
    without_icon = QuestionFactory(event=event, variant=QuestionVariant.STRING)

    assert str(with_icon.pk) in with_icon.icon_url
    assert without_icon.icon_url is None


def test_question_identifier_unique_per_event():
    event = EventFactory()
    generated = QuestionFactory(event=event)
    custom = QuestionFactory(event=event, identifier="MY-CUSTOM-ID")
    elsewhere = QuestionFactory(event=EventFactory(), identifier="MY-CUSTOM-ID")
    duplicate = QuestionFactory.build(event=event, identifier="MY-CUSTOM-ID")

    assert len(generated.identifier) == 8
    assert custom.identifier == "MY-CUSTOM-ID"
    assert elsewhere.identifier == "MY-CUSTOM-ID"
    with pytest.raises(ValidationError) as exc_info:
        duplicate.clean()
    assert list(exc_info.value.message_dict) == ["identifier"]
    with pytest.raises(IntegrityError):
        QuestionFactory(event=event, identifier="MY-CUSTOM-ID")


def test_question_get_instance_data_lists_options():
    string_q = QuestionFactory(variant=QuestionVariant.STRING)
    choices_q = QuestionFactory(event=string_q.event, variant=QuestionVariant.CHOICES)
    empty_choices_q = QuestionFactory(
        event=string_q.event, variant=QuestionVariant.CHOICES
    )
    AnswerOptionFactory(question=choices_q, answer="Option A")
    AnswerOptionFactory(question=choices_q, answer="Option B")

    string_data = string_q.get_instance_data()

    assert string_data["variant"] == QuestionVariant.STRING
    assert string_data["target"] == QuestionTarget.SUBMISSION
    assert "options" not in string_data
    assert choices_q.get_instance_data()["options"] == "- Option A\n- Option B"
    assert "options" not in empty_choices_q.get_instance_data()


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, False), (1, True)), ids=("down", "up")
)
def test_question_move_swaps_positions(move_index, up):
    event = EventFactory()
    questions = [QuestionFactory(event=event, position=i) for i in range(2)]

    questions[move_index].move(up=up)

    for q in questions:
        q.refresh_from_db()
    assert questions[0].position == 1
    assert questions[1].position == 0


def test_answer_option_properties():
    option = AnswerOptionFactory(answer="Yes, please")

    assert str(option) == "Yes, please"
    assert option.event == option.question.event
    assert option.log_parent == option.question


def test_answer_option_identifier_unique_per_question():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    generated = AnswerOptionFactory(question=question)
    custom = AnswerOptionFactory(question=question, identifier="OPT-CUSTOM")
    duplicate = AnswerOptionFactory.build(question=question, identifier="OPT-CUSTOM")
    codes = AnswerOption.generate_unique_codes(50, question=question)

    assert len(generated.identifier) == 8
    assert custom.identifier == "OPT-CUSTOM"
    assert len(set(codes)) == 50
    assert all(len(c) == 8 for c in codes)
    with pytest.raises(ValidationError) as exc_info:
        duplicate.clean()
    assert list(exc_info.value.message_dict) == ["identifier"]
    with pytest.raises(IntegrityError):
        AnswerOptionFactory(question=question, identifier="OPT-CUSTOM")


def test_answer_for_submission():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION, variant=QuestionVariant.FILE
    )
    submission = SubmissionFactory(event=question.event)
    other_submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(
        question=question, submission=submission, speaker=None, answer="42"
    )

    log = answer.log_action("pretalx.test.action")
    explicit = answer.log_action("pretalx.test.action", content_object=other_submission)
    path = answer_file_path(answer, "document.pdf")

    assert str(answer) == f"Answer(question={question.question}, answer=42)"
    assert answer.event == question.event
    assert answer.log_parent == submission
    assert log.content_object == submission
    assert explicit.content_object == other_submission
    assert re.fullmatch(
        rf"{question.event.slug}/question_uploads/q{question.pk}-{submission.code}_\w+\.pdf",
        path,
    )


def test_answer_for_speaker():
    question = QuestionFactory(
        target=QuestionTarget.SPEAKER, variant=QuestionVariant.FILE
    )
    speaker = SpeakerFactory(event=question.event)
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    log = answer.log_action("pretalx.test.action")
    path = answer_file_path(answer, "photo.jpg")

    assert answer.log_parent == speaker
    assert log.content_object == speaker
    assert re.fullmatch(
        rf"{question.event.slug}/question_uploads/q{question.pk}-{speaker.code}_\w+\.jpg",
        path,
    )


def test_answer_for_reviewer():
    question = QuestionFactory(
        target=QuestionTarget.REVIEWER, variant=QuestionVariant.FILE
    )
    review = ReviewFactory(submission__event=question.event)
    answer = AnswerFactory(question=question, review=review, submission=None)

    log = answer.log_action("pretalx.test.action")
    path = answer_file_path(answer, "notes.txt")

    assert answer.log_parent == review
    assert log.content_object == review
    assert re.fullmatch(
        rf"{question.event.slug}/question_uploads/q{question.pk}-r{review.pk}_\w+\.txt",
        path,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    (("True", True), ("False", False), ("other", None)),
    ids=("true", "false", "other"),
)
def test_answer_boolean_answer(value, expected):
    answer = AnswerFactory(answer=value)
    assert answer.boolean_answer is expected


@pytest.mark.parametrize(
    ("variant", "answer_text", "expected"),
    (
        (QuestionVariant.NUMBER, "42", "42"),
        (QuestionVariant.STRING, "hello", "hello"),
        (QuestionVariant.TEXT, "", ""),
        (QuestionVariant.URL, "https://example.com", "https://example.com"),
        (QuestionVariant.BOOLEAN, "True", "Yes"),
        (QuestionVariant.BOOLEAN, "False", "No"),
        (QuestionVariant.BOOLEAN, "None", ""),
    ),
)
def test_answer_answer_string(variant, answer_text, expected):
    question = QuestionFactory(variant=variant)
    answer = AnswerFactory(question=question, answer=answer_text)
    result = answer.answer_string
    assert str(result) == expected


def test_answer_answer_string_joins_options():
    event = EventFactory()
    single = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    multiple = QuestionFactory(event=event, variant=QuestionVariant.MULTIPLE)
    single_answer = AnswerFactory(question=single)
    single_answer.options.add(AnswerOptionFactory(question=single, answer="Option A"))
    multiple_answer = AnswerFactory(question=multiple)
    multiple_answer.options.add(
        AnswerOptionFactory(question=multiple, answer="A"),
        AnswerOptionFactory(question=multiple, answer="B"),
    )

    assert single_answer.answer_string == "Option A"
    assert multiple_answer.answer_string == "A, B"


@pytest.mark.parametrize(
    ("variant", "answer_text", "expected"),
    (
        (QuestionVariant.DATE, "2024-03-07", "2024-03-07"),
        (QuestionVariant.DATETIME, "2024-03-07 23:30:00+00:00", "2024-03-08 10:30"),
        (QuestionVariant.DATETIME, "2024-03-07T10:15", "2024-03-07 10:15"),
        (QuestionVariant.DATE, "not a date", "not a date"),
        (
            QuestionVariant.DATETIME,
            "9999-12-31 23:00:00-12:00",
            "9999-12-31 23:00:00-12:00",
        ),
    ),
    ids=("date", "datetime_in_event_tz", "naive_datetime", "garbage", "overflow"),
)
def test_answer_answer_string_date_variants(variant, answer_text, expected):
    question = QuestionFactory(variant=variant, event__timezone="Australia/Sydney")
    answer = AnswerFactory(question=question, answer=answer_text)

    with scope(event=question.event):
        answer = Answer.objects.get(pk=answer.pk)
        assert answer.answer_string == expected


def test_answer_file_name_strips_path():
    question = QuestionFactory(variant=QuestionVariant.FILE)
    answer = AnswerFactory(question=question, answer="")

    assert answer.file_name == ""
    assert answer.answer_string == ""

    answer.answer_file.name = "democon/question_uploads/q1-ABCDEF-xyz.pdf"
    assert answer.file_name == "q1-ABCDEF-xyz.pdf"


@pytest.mark.parametrize(
    ("answer_text", "expected"), (("yes", True), ("", False)), ids=("answered", "empty")
)
def test_answer_is_answered(answer_text, expected):
    answer = AnswerFactory(
        question=QuestionFactory(variant=QuestionVariant.STRING), answer=answer_text
    )
    assert answer.is_answered is expected


def test_answer_file_deleted_on_replace_and_delete(django_capture_on_commit_callbacks):
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.FILE, target=QuestionTarget.SUBMISSION
    )
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        answer = AnswerFactory(question=question, submission=submission, answer="")
        answer.answer_file.save("old.pdf", ContentFile(b"old"), save=True)
        old_path = answer.answer_file.name
        assert default_storage.exists(old_path)

        with django_capture_on_commit_callbacks(execute=True):
            answer.answer_file.save("new.pdf", ContentFile(b"new"), save=True)
        new_path = answer.answer_file.name
        assert not default_storage.exists(old_path)
        assert default_storage.exists(new_path)

        with django_capture_on_commit_callbacks(execute=True):
            answer.delete()

    assert not default_storage.exists(new_path)
