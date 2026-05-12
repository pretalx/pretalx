# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretalx.submission.domain.question import (
    apply_uploaded_options,
    delete_question,
    export_answer_files,
    reorder_questions,
    replace_question_options,
    save_answer,
    set_question_active,
)
from pretalx.submission.models import (
    Answer,
    AnswerOption,
    Question,
    QuestionTarget,
    QuestionVariant,
)
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
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


def test_export_answer_files_non_file_question():
    question = QuestionFactory(variant=QuestionVariant.STRING)
    cached_file = CachedFileFactory()

    result = export_answer_files(question=question, cached_file=cached_file)

    assert result is None
    cached_file.refresh_from_db()
    assert not cached_file.file


def test_export_answer_files_no_answers():
    question = QuestionFactory(variant=QuestionVariant.FILE)
    cached_file = CachedFileFactory()

    result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        assert zf.namelist() == []


def test_export_answer_files_creates_zip():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        answer = AnswerFactory(
            submission=submission, question=question, answer="doc.pdf"
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"pdf content"))

    cached_file = CachedFileFactory()
    with scope(event=event):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b"pdf content"


def test_export_answer_files_multiple_answers():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = AnswerFactory(submission=submission1, question=question, answer="doc.pdf")
        a1.answer_file.save("doc.pdf", ContentFile(b"content 1"))
        a2 = AnswerFactory(submission=submission2, question=question, answer="doc.pdf")
        a2.answer_file.save("doc.pdf", ContentFile(b"content 2"))

    cached_file = CachedFileFactory()
    with scope(event=event):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        contents = {zf.read(n) for n in names}
        assert contents == {b"content 1", b"content 2"}


def test_export_answer_files_deduplicates_filenames():
    """When safe_filename produces identical basenames, counter suffixes are added."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = AnswerFactory(submission=s1, question=question, answer="doc.pdf")
        a1.answer_file.save("doc.pdf", ContentFile(b"file 1"))
        a2 = AnswerFactory(submission=s2, question=question, answer="doc.pdf")
        a2.answer_file.save("doc.pdf", ContentFile(b"file 2"))

    cached_file = CachedFileFactory()
    with (
        scope(event=event),
        patch(
            "pretalx.submission.domain.question.safe_filename", return_value="doc.pdf"
        ),
    ):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = sorted(zf.namelist())
        assert names == ["doc.pdf", "doc_1.pdf"]


def test_export_answer_files_skips_empty_answer_file():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        AnswerFactory(
            submission=submission,
            question=question,
            answer="placeholder",
            answer_file="",
        )

    cached_file = CachedFileFactory()
    with scope(event=event):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        assert zf.namelist() == []


def test_export_answer_files_handles_unreadable_file():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        answer = AnswerFactory(
            submission=submission, question=question, answer="doc.pdf"
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"content"))

    cached_file = CachedFileFactory()
    with (
        scope(event=event),
        patch(
            "pretalx.submission.domain.question.shutil.copyfileobj",
            side_effect=OSError("Permission denied"),
        ),
    ):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b""


def test_replace_question_options_replaces_existing():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question, answer="Old A")
    AnswerOptionFactory(question=question, answer="Old B")

    replace_question_options(
        question=question, options_data=[{"answer": "New A"}, {"answer": "New B"}]
    )

    options = sorted(str(a) for a in question.options.values_list("answer", flat=True))
    assert options == ["New A", "New B"]


def test_replace_question_options_empty_clears_existing():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)

    replace_question_options(question=question, options_data=[])

    assert question.options.count() == 0


def test_export_answer_files_general_exception():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    s1 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = AnswerFactory(submission=s1, question=question, answer="doc.pdf")
        a1.answer_file.save("doc.pdf", ContentFile(b"content"))

    cached_file = CachedFileFactory()
    with (
        scope(event=event),
        patch(
            "pretalx.submission.domain.question.zipfile.ZipFile",
            side_effect=RuntimeError("disk full"),
        ),
    ):
        result = export_answer_files(question=question, cached_file=cached_file)

    assert result is None


def test_delete_question_removes_options_and_log_entries():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    with scope(event=event):
        question.log_action(".create", orga=True)
        assert question.logged_actions().count() >= 1
        option_count = question.options.count()

    assert option_count == 2

    with scope(event=event):
        delete_question(question)

        assert not Question.all_objects.filter(pk=question.pk).exists()
        assert not AnswerOption.objects.filter(question_id=question.pk).exists()


def test_delete_question_raises_protected_when_answered():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.STRING)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        AnswerFactory(question=question, submission=submission, answer="x")

    with scope(event=event), pytest.raises(ProtectedError):
        delete_question(question)

    with scope(event=event):
        assert Question.all_objects.filter(pk=question.pk).exists()


def test_apply_uploaded_options_noop_for_empty():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)

    with scope(event=event):
        apply_uploaded_options(question=question, options=None, replace=True)

        assert question.options.count() == 0


def test_apply_uploaded_options_replace_deletes_answers_and_options():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        old = AnswerOptionFactory(question=question, answer="Old")
        AnswerFactory(question=question, answer="Old")

        apply_uploaded_options(
            question=question, options=["New A", "New B"], replace=True
        )

        positions = list(
            question.options.order_by("position").values_list("answer", flat=True)
        )
        assert positions == ["New A", "New B"]
        assert question.answers.count() == 0
        assert not question.options.filter(pk=old.pk).exists()


def test_apply_uploaded_options_merge_adds_only_new_and_updates_positions():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        existing = AnswerOptionFactory(question=question, answer="A", position=5)

        apply_uploaded_options(question=question, options=["A", "B"], replace=False)

        existing.refresh_from_db()
        assert existing.position == 1
        assert question.options.count() == 2
        new = question.options.get(answer="B")
        assert new.position == 2


def test_apply_uploaded_options_merge_no_new_when_all_exist():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        AnswerOptionFactory(question=question, answer="Only", position=3)

        apply_uploaded_options(question=question, options=["Only"], replace=False)

        assert question.options.count() == 1
        assert question.options.first().position == 1


def test_apply_uploaded_options_merge_i18n_on_multilingual_event():
    event = EventFactory(locale_array="en,de", content_locale_array="en,de")
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        AnswerOptionFactory(question=question, answer="Existing", position=1)

        options = [
            LazyI18nString({"en": "Existing", "de": "Bestehend"}),
            LazyI18nString({"en": "New", "de": "Neu"}),
        ]
        apply_uploaded_options(question=question, options=options, replace=False)

        assert question.options.count() == 2


def test_set_question_active_activates_and_logs():
    event = EventFactory()
    user = UserFactory()
    question = QuestionFactory(event=event, active=False)

    with scope(event=event):
        set_question_active(question, active=True, person=user)

        question.refresh_from_db()
        assert question.active is True
        log = question.logged_actions().first()
        assert log.action_type == "pretalx.question.activate"
        assert log.person == user


def test_set_question_active_deactivates_and_logs():
    event = EventFactory()
    user = UserFactory()
    question = QuestionFactory(event=event, active=True)

    with scope(event=event):
        set_question_active(question, active=False, person=user)

        question.refresh_from_db()
        assert question.active is False
        log = question.logged_actions().first()
        assert log.action_type == "pretalx.question.deactivate"


def test_set_question_active_no_op_when_unchanged():
    event = EventFactory()
    question = QuestionFactory(event=event, active=True)

    with scope(event=event):
        set_question_active(question, active=True)
        assert not question.logged_actions().exists()


def test_reorder_questions_updates_positions_and_logs_once():
    event = EventFactory()
    user = UserFactory()
    with scope(event=event):
        q1 = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=0)
        q2 = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=1)

        reorder_questions(
            event,
            target=QuestionTarget.SUBMISSION,
            ordered_positions=[(0, q2.pk), (1, q1.pk)],
            person=user,
        )

        q1.refresh_from_db()
        q2.refresh_from_db()
        assert q1.position == 1
        assert q2.position == 0
        logs = event.logged_actions().filter(action_type="pretalx.question.reorder")
        assert logs.count() == 1


def test_reorder_questions_no_changes_skips_log():
    event = EventFactory()
    with scope(event=event):
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=0)

        reorder_questions(
            event, target=QuestionTarget.SUBMISSION, ordered_positions=[(0, q.pk)]
        )

        assert (
            not event.logged_actions()
            .filter(action_type="pretalx.question.reorder")
            .exists()
        )


def test_reorder_questions_skips_unknown_ids():
    event = EventFactory()
    with scope(event=event):
        q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=0)

        reorder_questions(
            event,
            target=QuestionTarget.SUBMISSION,
            ordered_positions=[(0, 999999), (1, q.pk)],
        )
        q.refresh_from_db()
        assert q.position == 1
