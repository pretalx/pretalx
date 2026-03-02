# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Answer, AnswerOption, Question, Submission
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


def test_question_variant_short_answers():
    assert set(QuestionVariant.short_answers) | set(
        QuestionVariant.long_answers
    ) == set(QuestionVariant.values)
    assert not set(QuestionVariant.short_answers) & set(QuestionVariant.long_answers)


def test_question_variant_long_answers():
    assert QuestionVariant.long_answers == ("text",)


@pytest.mark.parametrize(
    "cls",
    (QuestionVariant, QuestionTarget, QuestionRequired, QuestionIcon),
    ids=("variant", "target", "required", "icon"),
)
def test_question_choices_get_max_length(cls):
    assert cls.get_max_length() == max(len(val) for val in cls.values)


def test_question_manager_excludes_inactive():
    event = EventFactory()
    active_q = QuestionFactory(event=event, active=True)
    QuestionFactory(event=event, active=False)

    result = list(Question.objects.filter(event=event))

    assert result == [active_q]


def test_question_manager_excludes_reviewer_target():
    event = EventFactory()
    submission_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    QuestionFactory(event=event, target=QuestionTarget.REVIEWER)

    result = list(Question.objects.filter(event=event))

    assert result == [submission_q]


def test_question_all_objects_includes_everything():
    event = EventFactory()
    active_q = QuestionFactory(event=event, active=True)
    inactive_q = QuestionFactory(event=event, active=False)
    reviewer_q = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)

    result = set(Question.all_objects.filter(event=event))

    assert result == {active_q, inactive_q, reviewer_q}


def test_question_str():
    question = QuestionFactory(question="What is your T-shirt size?")
    assert str(question) == "What is your T-shirt size?"


def test_question_log_properties():
    question = QuestionFactory()
    assert question.log_prefix == "pretalx.question"
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
    ((timedelta(days=-1), True), (timedelta(days=1), False)),
    ids=("past", "future"),
)
def test_question_read_only(freeze_delta, expected):
    question = QuestionFactory(freeze_after=tz_now() + freeze_delta)
    assert question.read_only is expected


def test_question_read_only_when_no_freeze_after():
    question = QuestionFactory(freeze_after=None)
    assert not question.read_only


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


def test_question_icon_url_when_show_icon():
    question = QuestionFactory(variant=QuestionVariant.URL, icon=QuestionIcon.GITHUB)
    assert str(question.pk) in question.icon_url


def test_question_icon_url_none_when_no_icon():
    question = QuestionFactory(variant=QuestionVariant.STRING)
    assert question.icon_url is None


def test_question_clean_identifier_raises_on_duplicate():
    event = EventFactory()
    QuestionFactory(event=event, identifier="DUPE-ID")

    with pytest.raises(ValidationError):
        Question.clean_identifier(event, "DUPE-ID")


def test_question_clean_identifier_case_insensitive():
    event = EventFactory()
    QuestionFactory(event=event, identifier="My-Id")

    with pytest.raises(ValidationError):
        Question.clean_identifier(event, "my-id")


def test_question_clean_identifier_allows_same_instance():
    event = EventFactory()
    question = QuestionFactory(event=event, identifier="MY-ID")
    Question.clean_identifier(event, "MY-ID", instance=question)


@pytest.mark.parametrize("code", ("", None), ids=("empty", "none"))
def test_question_clean_identifier_returns_early_for_falsy_code(code):
    Question.clean_identifier(EventFactory(), code)


def test_question_get_order_queryset():
    event = EventFactory()
    q2 = QuestionFactory(event=event, position=1)
    q1 = QuestionFactory(event=event, position=0)

    result = list(Question.get_order_queryset(event))

    assert result == [q1, q2]


def test_question_get_order_queryset_includes_inactive():
    """get_order_queryset uses all_objects, including inactive questions."""
    event = EventFactory()
    active = QuestionFactory(event=event, position=0, active=True)
    inactive = QuestionFactory(event=event, position=1, active=False)

    result = list(Question.get_order_queryset(event))

    assert result == [active, inactive]


def test_question_missing_answers_submission_all_missing():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    SubmissionFactory(event=event)
    SubmissionFactory(event=event)

    with scope(event=event):
        assert question.missing_answers() == 2


def test_question_missing_answers_submission_some_answered():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=event)
    SubmissionFactory(event=event)
    AnswerFactory(question=question, submission=submission, speaker=None)

    with scope(event=event):
        assert question.missing_answers() == 1


def test_question_missing_answers_speaker():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        assert question.missing_answers() == 1


def test_question_missing_answers_speaker_answered():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    AnswerFactory(question=question, speaker=speaker, submission=None)

    with scope(event=event):
        assert question.missing_answers() == 0


def test_question_missing_answers_reviewer_returns_zero():
    question = QuestionFactory(target=QuestionTarget.REVIEWER)

    with scope(event=question.event):
        assert question.missing_answers() == 0


def test_question_missing_answers_with_filter_talks():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    sub1 = SubmissionFactory(event=event)
    SubmissionFactory(event=event)

    with scope(event=event):
        filtered = Submission.objects.filter(pk=sub1.pk)
        assert question.missing_answers(filter_talks=filtered) == 1


def test_question_missing_answers_with_filter_speakers():
    event = EventFactory()
    question = QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        filtered = SpeakerProfile.objects.filter(pk=speaker.pk)
        assert question.missing_answers(filter_speakers=filtered) == 1


def test_question_get_instance_data_for_string_variant():
    question = QuestionFactory(variant=QuestionVariant.STRING)
    data = question.get_instance_data()

    assert data["variant"] == QuestionVariant.STRING
    assert data["target"] == QuestionTarget.SUBMISSION
    assert "options" not in data


def test_question_get_instance_data_with_choice_options():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question, answer="Option A")
    AnswerOptionFactory(question=question, answer="Option B")

    data = question.get_instance_data()

    assert data["options"] == "- Option A\n- Option B"


def test_question_get_instance_data_choices_no_options():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)

    data = question.get_instance_data()

    assert "options" not in data


def test_question_identifier_auto_generated():
    question = QuestionFactory()
    assert len(question.identifier) == 8


def test_question_identifier_custom():
    question = QuestionFactory(identifier="MY-CUSTOM-ID")
    assert question.identifier == "MY-CUSTOM-ID"


def test_question_identifier_unique_per_event():
    event = EventFactory()
    QuestionFactory(event=event, identifier="SAME-ID")

    with pytest.raises(IntegrityError):
        QuestionFactory(event=event, identifier="SAME-ID")


def test_question_identifier_same_id_different_events():
    event1 = EventFactory()
    event2 = EventFactory()
    QuestionFactory(event=event1, identifier="SHARED-ID")
    q2 = QuestionFactory(event=event2, identifier="SHARED-ID")
    assert q2.identifier == "SHARED-ID"


def test_question_ordering_by_position():
    event = EventFactory()
    q2 = QuestionFactory(event=event, position=2)
    q1 = QuestionFactory(event=event, position=1)

    result = list(Question.all_objects.filter(event=event).order_by("position", "id"))

    assert result == [q1, q2]


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


def test_answer_option_str():
    option = AnswerOptionFactory(answer="Yes, please")
    assert str(option) == "Yes, please"


def test_answer_option_event():
    option = AnswerOptionFactory()
    assert option.event == option.question.event


def test_answer_option_log_properties():
    option = AnswerOptionFactory()
    assert option.log_prefix == "pretalx.question.option"
    assert option.log_parent == option.question


def test_answer_option_identifier_auto_generated():
    option = AnswerOptionFactory()
    assert len(option.identifier) == 8


def test_answer_option_identifier_custom():
    option = AnswerOptionFactory(identifier="OPT-CUSTOM")
    assert option.identifier == "OPT-CUSTOM"


def test_answer_option_identifier_unique_per_question():
    option1 = AnswerOptionFactory(identifier="SAME-OPT")
    with pytest.raises(IntegrityError):
        AnswerOptionFactory(question=option1.question, identifier="SAME-OPT")


def test_answer_option_clean_identifier_raises_on_duplicate():
    option = AnswerOptionFactory(identifier="DUPE")
    with pytest.raises(ValidationError):
        AnswerOption.clean_identifier(option.question, "DUPE")


def test_answer_option_clean_identifier_case_insensitive():
    option = AnswerOptionFactory(identifier="MyOpt")
    with pytest.raises(ValidationError):
        AnswerOption.clean_identifier(option.question, "myopt")


def test_answer_option_clean_identifier_allows_same_instance():
    option = AnswerOptionFactory(identifier="MY-OPT")
    AnswerOption.clean_identifier(option.question, "MY-OPT", instance=option)


@pytest.mark.parametrize("code", ("", None), ids=("empty", "none"))
def test_answer_option_clean_identifier_returns_early_for_falsy_code(code):
    AnswerOption.clean_identifier(QuestionFactory(), code)


def test_answer_option_generate_unique_codes_batch():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)

    codes = AnswerOption.generate_unique_codes(50, question=question)

    assert len(codes) == 50
    assert len(set(codes)) == 50
    assert all(len(c) == 8 for c in codes)


def test_answer_str():
    answer = AnswerFactory(answer="42")
    assert str(answer) == f"Answer(question={answer.question.question}, answer=42)"


def test_answer_event():
    answer = AnswerFactory()
    assert answer.event == answer.question.event


def test_answer_log_parent_submission():
    question = QuestionFactory(target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission, speaker=None)
    assert answer.log_prefix == "pretalx.submission.answer"
    assert answer.log_parent == submission


def test_answer_log_parent_speaker():
    question = QuestionFactory(target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=question.event)
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)
    assert answer.log_parent == speaker


def test_answer_log_parent_reviewer():
    question = QuestionFactory(target=QuestionTarget.REVIEWER)
    review = ReviewFactory(submission__event=question.event)
    answer = AnswerFactory(question=question, review=review, submission=None)
    assert answer.log_parent == review


def test_answer_remove_deletes_answer():
    answer = AnswerFactory()
    pk = answer.pk

    answer.remove()

    assert not Answer.objects.filter(pk=pk).exists()


def test_answer_remove_clears_options():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    option = AnswerOptionFactory(question=question)
    answer = AnswerFactory(question=question)
    answer.options.add(option)

    answer.remove()

    assert not option.answers.exists()


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


def test_answer_answer_string_file_without_file():
    question = QuestionFactory(variant=QuestionVariant.FILE)
    answer = AnswerFactory(question=question, answer="")
    assert answer.answer_string == ""


def test_answer_answer_string_choices():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    option = AnswerOptionFactory(question=question, answer="Option A")
    answer = AnswerFactory(question=question)
    answer.options.add(option)

    assert answer.answer_string == "Option A"


def test_answer_answer_string_multiple_choice():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="A")
    opt2 = AnswerOptionFactory(question=question, answer="B")
    answer = AnswerFactory(question=question)
    answer.options.add(opt1, opt2)

    assert answer.answer_string == "A, B"


def test_answer_answer_string_unknown_variant():
    question = QuestionFactory(variant="date")
    answer = AnswerFactory(question=question, answer="2024-01-01")
    assert answer.answer_string is None


@pytest.mark.parametrize(
    ("answer_text", "expected"), (("yes", True), ("", False)), ids=("answered", "empty")
)
def test_answer_is_answered(answer_text, expected):
    answer = AnswerFactory(
        question=QuestionFactory(variant=QuestionVariant.STRING), answer=answer_text
    )
    assert answer.is_answered is expected


def test_answer_log_action_sets_content_object_for_submission():
    question = QuestionFactory(target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission, speaker=None)

    log = answer.log_action("pretalx.test.action")

    assert log.content_object == submission


def test_answer_log_action_sets_content_object_for_speaker():
    question = QuestionFactory(target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=question.event)
    answer = AnswerFactory(question=question, speaker=speaker, submission=None)

    log = answer.log_action("pretalx.test.action")

    assert log.content_object == speaker


def test_answer_log_action_sets_content_object_for_reviewer():
    question = QuestionFactory(target=QuestionTarget.REVIEWER)
    review = ReviewFactory(submission__event=question.event)
    answer = AnswerFactory(question=question, review=review, submission=None)

    log = answer.log_action("pretalx.test.action")

    assert log.content_object == review


def test_answer_log_action_respects_explicit_content_object():
    question = QuestionFactory(target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission, speaker=None)
    other_submission = SubmissionFactory(event=question.event)

    log = answer.log_action("pretalx.test.action", content_object=other_submission)

    assert log.content_object == other_submission


def test_answer_file_path_submission():
    question = QuestionFactory(
        variant=QuestionVariant.FILE, target=QuestionTarget.SUBMISSION
    )
    submission = SubmissionFactory(event=question.event)
    answer = Answer(question=question, submission=submission, answer="")

    path = answer_file_path(answer, "document.pdf")

    assert path.startswith(f"{question.event.slug}/question_uploads/")
    assert f"q{question.pk}-{submission.code}" in path
    assert path.endswith(".pdf")
    assert "document" not in path


def test_answer_file_path_speaker():
    question = QuestionFactory(
        variant=QuestionVariant.FILE, target=QuestionTarget.SPEAKER
    )
    speaker = SpeakerFactory(event=question.event)
    answer = Answer(question=question, speaker=speaker, answer="")

    path = answer_file_path(answer, "photo.jpg")

    assert path.startswith(f"{question.event.slug}/question_uploads/")
    assert f"q{question.pk}-{speaker.code}" in path
    assert path.endswith(".jpg")


def test_answer_file_path_reviewer():
    question = QuestionFactory(
        variant=QuestionVariant.FILE, target=QuestionTarget.REVIEWER
    )
    review = ReviewFactory(submission__event=question.event)
    answer = Answer(question=question, review=review, answer="")

    path = answer_file_path(answer, "notes.txt")

    assert path.startswith(f"{question.event.slug}/question_uploads/")
    assert f"q{question.pk}-r{review.pk}" in path
    assert path.endswith(".txt")


def test_answer_file_deleted_on_answer_delete():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.FILE, target=QuestionTarget.SUBMISSION
    )
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        answer = AnswerFactory(question=question, submission=submission, answer="")
        answer.answer_file.save("test.pdf", ContentFile(b"test content"), save=True)
        file_path = answer.answer_file.name

        assert default_storage.exists(file_path)

        answer.delete()

    assert not default_storage.exists(file_path)


def test_answer_file_deleted_on_file_replace():
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

        answer.answer_file.save("new.pdf", ContentFile(b"new"), save=True)
        new_path = answer.answer_file.name

    assert not default_storage.exists(old_path)
    assert default_storage.exists(new_path)

    with scope(event=event):
        answer.delete()
