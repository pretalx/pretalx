# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.submission.domain.question import save_answer
from pretalx.submission.models import (
    Answer,
    AnswerOption,
    QuestionTarget,
    QuestionVariant,
)
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_save_answer_creates_for_submission():
    submission = SubmissionFactory()
    question = QuestionFactory(
        event=submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SUBMISSION,
    )

    answer = save_answer(question=question, value="My answer", target_object=submission)

    assert answer.pk is not None
    assert answer.answer == "My answer"
    assert answer.submission == submission


def test_save_answer_updates_existing():
    submission = SubmissionFactory()
    question = QuestionFactory(
        event=submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SUBMISSION,
    )
    existing = AnswerFactory(question=question, submission=submission, answer="Old")

    answer = save_answer(
        question=question,
        value="New answer",
        target_object=submission,
        existing=existing,
    )

    assert answer.pk == existing.pk
    existing.refresh_from_db()
    assert existing.answer == "New answer"


def test_save_answer_deletes_on_empty_value():
    submission = SubmissionFactory()
    question = QuestionFactory(
        event=submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SUBMISSION,
    )
    existing = AnswerFactory(question=question, submission=submission, answer="Old")

    result = save_answer(
        question=question, value="", target_object=submission, existing=existing
    )

    assert result is None
    assert not Answer.objects.filter(pk=existing.pk).exists()


def test_save_answer_noop_for_empty_value_without_existing():
    submission = SubmissionFactory()
    question = QuestionFactory(
        event=submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SUBMISSION,
    )

    result = save_answer(question=question, value="", target_object=submission)

    assert result is None
    assert not Answer.objects.filter(question=question).exists()


def test_save_answer_creates_for_speaker():
    speaker = SpeakerFactory()
    question = QuestionFactory(
        event=speaker.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SPEAKER,
    )

    answer = save_answer(
        question=question, value="Speaker answer", target_object=speaker
    )

    assert answer.pk is not None
    assert answer.speaker == speaker
    assert answer.answer == "Speaker answer"


def test_save_answer_creates_for_review():
    review = ReviewFactory()
    question = QuestionFactory(
        event=review.submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.REVIEWER,
    )

    answer = save_answer(
        question=question, value="Reviewer answer", target_object=review
    )

    assert answer.pk is not None
    assert answer.review == review


def test_save_answer_choice_creates_with_option():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    option = AnswerOptionFactory(question=question, answer="Selected")
    submission = SubmissionFactory(event=question.event)

    answer = save_answer(question=question, value=option, target_object=submission)

    assert answer.pk is not None
    assert answer.answer == option.answer
    assert list(answer.options.all()) == [option]


def test_save_answer_choice_update_clears_old_option():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    opt1 = AnswerOptionFactory(question=question, answer="Old")
    opt2 = AnswerOptionFactory(question=question, answer="New")
    submission = SubmissionFactory(event=question.event)
    existing = AnswerFactory(question=question, submission=submission)
    existing.options.add(opt1)

    answer = save_answer(
        question=question, value=opt2, target_object=submission, existing=existing
    )

    answer.refresh_from_db()
    assert list(answer.options.all()) == [opt2]
    assert answer.answer == opt2.answer


def test_save_answer_multiple_creates_with_options():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="A")
    opt2 = AnswerOptionFactory(question=question, answer="B")
    submission = SubmissionFactory(event=question.event)

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.filter(pk__in=[opt1.pk, opt2.pk]),
        target_object=submission,
    )

    assert answer.pk is not None
    assert set(answer.options.all()) == {opt1, opt2}
    assert answer.answer == "A, B"


def test_save_answer_multiple_update_clears():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="Old")
    opt2 = AnswerOptionFactory(question=question, answer="New")
    submission = SubmissionFactory(event=question.event)
    existing = AnswerFactory(question=question, submission=submission)
    existing.options.add(opt1)

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.filter(pk=opt2.pk),
        target_object=submission,
        existing=existing,
    )

    answer.refresh_from_db()
    assert list(answer.options.all()) == [opt2]


def test_save_answer_multiple_empty_iterable_clears_options():
    """An empty queryset (truthy as a value but with no rows) clears options
    without re-adding any — exercises the empty-options branch of
    ``_set_choice_options``."""
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt = AnswerOptionFactory(question=question, answer="Old")
    submission = SubmissionFactory(event=question.event)
    existing = AnswerFactory(question=question, submission=submission)
    existing.options.add(opt)

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.none(),
        target_object=submission,
        existing=existing,
    )

    answer.refresh_from_db()
    assert list(answer.options.all()) == []
    assert answer.answer == ""


def test_save_answer_file_creates_from_uploaded_file():
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    upload = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")

    answer = save_answer(question=question, value=upload, target_object=submission)

    assert answer.pk is not None
    assert answer.answer == "file://" + answer.answer_file.name
    with answer.answer_file.open("rb") as fp:
        assert fp.read() == b"content"


def test_save_answer_file_keeps_existing_when_value_is_path_string():
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    existing = AnswerFactory(
        question=question, submission=submission, answer="file://existing.pdf"
    )
    existing.answer_file.name = "existing.pdf"
    existing.save()
    original_file_name = existing.answer_file.name

    answer = save_answer(
        question=question,
        value="file://existing.pdf",
        target_object=submission,
        existing=existing,
    )

    answer.refresh_from_db()
    assert answer.answer == "file://existing.pdf"
    assert answer.answer_file.name == original_file_name


def test_answer_target_object_property_returns_correct_parent():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    review = ReviewFactory(submission=submission)
    sub_q = QuestionFactory(event=submission.event, target=QuestionTarget.SUBMISSION)
    spk_q = QuestionFactory(event=submission.event, target=QuestionTarget.SPEAKER)
    rev_q = QuestionFactory(event=submission.event, target=QuestionTarget.REVIEWER)

    sub_a = AnswerFactory(question=sub_q, submission=submission)
    spk_a = AnswerFactory(question=spk_q, speaker=speaker)
    rev_a = AnswerFactory(question=rev_q, review=review)

    assert sub_a.target_object == submission
    assert spk_a.target_object == speaker
    assert rev_a.target_object == review


def test_answer_target_object_setter_assigns_correct_fk():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    review = ReviewFactory(submission=submission)
    sub_q = QuestionFactory(event=submission.event, target=QuestionTarget.SUBMISSION)
    spk_q = QuestionFactory(event=submission.event, target=QuestionTarget.SPEAKER)
    rev_q = QuestionFactory(event=submission.event, target=QuestionTarget.REVIEWER)

    sub_a = Answer(question=sub_q)
    sub_a.target_object = submission
    spk_a = Answer(question=spk_q)
    spk_a.target_object = speaker
    rev_a = Answer(question=rev_q)
    rev_a.target_object = review

    assert sub_a.submission == submission
    assert sub_a.speaker is None
    assert sub_a.review is None
    assert spk_a.speaker == speaker
    assert spk_a.submission is None
    assert spk_a.review is None
    assert rev_a.review == review
    assert rev_a.submission is None
    assert rev_a.speaker is None
