# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django_scopes import scope
from i18nfield.strings import LazyI18nString
from PIL import ExifTags, Image

from pretalx.common.tasks import task_process_image
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
    SubmissionStates,
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


def test_save_answer_creates_updates_and_deletes_string_answer():
    submission = SubmissionFactory()
    question = QuestionFactory(
        event=submission.event,
        variant=QuestionVariant.STRING,
        target=QuestionTarget.SUBMISSION,
    )

    assert save_answer(question=question, value="", target_object=submission) is None
    assert not Answer.objects.filter(question=question).exists()

    answer = save_answer(question=question, value="My answer", target_object=submission)

    assert answer.answer == "My answer"
    assert answer.submission == submission
    assert list(Answer.objects.filter(question=question)) == [answer]

    updated = save_answer(
        question=question, value="New answer", target_object=submission, existing=answer
    )

    assert updated.pk == answer.pk
    assert Answer.objects.get(pk=answer.pk).answer == "New answer"

    assert (
        save_answer(
            question=question, value="", target_object=submission, existing=updated
        )
        is None
    )
    assert not Answer.objects.filter(pk=answer.pk).exists()


def test_save_answer_assigns_target_object_per_question_target():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    review = ReviewFactory(submission=submission)
    sub_q = QuestionFactory(event=submission.event, target=QuestionTarget.SUBMISSION)
    spk_q = QuestionFactory(event=submission.event, target=QuestionTarget.SPEAKER)
    rev_q = QuestionFactory(event=submission.event, target=QuestionTarget.REVIEWER)

    sub_a = save_answer(question=sub_q, value="Sub", target_object=submission)
    spk_a = save_answer(question=spk_q, value="Speaker", target_object=speaker)
    rev_a = save_answer(question=rev_q, value="Review", target_object=review)

    assert (sub_a.submission, sub_a.speaker, sub_a.review) == (submission, None, None)
    assert (spk_a.submission, spk_a.speaker, spk_a.review) == (None, speaker, None)
    assert (rev_a.submission, rev_a.speaker, rev_a.review) == (None, None, review)
    assert sub_a.target_object == submission
    assert spk_a.target_object == speaker
    assert rev_a.target_object == review
    assert [a.answer for a in (sub_a, spk_a, rev_a)] == ["Sub", "Speaker", "Review"]


def test_save_answer_choice_creates_and_replaces_option():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    opt1 = AnswerOptionFactory(question=question, answer="Old")
    opt2 = AnswerOptionFactory(question=question, answer="New")
    submission = SubmissionFactory(event=question.event)

    answer = save_answer(question=question, value=opt1, target_object=submission)

    assert answer.answer == "Old"
    assert list(answer.options.all()) == [opt1]

    answer = save_answer(
        question=question, value=opt2, target_object=submission, existing=answer
    )

    answer.refresh_from_db(fields=["answer"])
    assert list(answer.options.all()) == [opt2]
    assert answer.answer == "New"


def test_save_answer_multiple_creates_replaces_and_clears_options():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="A")
    opt2 = AnswerOptionFactory(question=question, answer="B")
    submission = SubmissionFactory(event=question.event)

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.filter(pk__in=[opt1.pk, opt2.pk]),
        target_object=submission,
    )

    assert set(answer.options.all()) == {opt1, opt2}
    assert answer.answer == "A, B"

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.filter(pk=opt2.pk),
        target_object=submission,
        existing=answer,
    )

    answer.refresh_from_db(fields=["answer"])
    assert list(answer.options.all()) == [opt2]
    assert answer.answer == "B"

    answer = save_answer(
        question=question,
        value=AnswerOption.objects.none(),
        target_object=submission,
        existing=answer,
    )

    answer.refresh_from_db(fields=["answer"])
    assert list(answer.options.all()) == []
    assert answer.answer == ""


def test_save_answer_file_creates_from_upload_and_keeps_path_string(
    django_capture_on_commit_callbacks,
):
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    upload = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")

    with (
        patch("pretalx.common.models.mixins.task_process_image.apply_async") as queue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        answer = save_answer(question=question, value=upload, target_object=submission)

    assert not queue.called
    stored_name = answer.answer_file.name
    assert answer.answer == "file://" + stored_name
    with answer.answer_file.open("rb") as fp:
        assert fp.read() == b"content"

    answer = save_answer(
        question=question,
        value="file://" + stored_name,
        target_object=submission,
        existing=answer,
    )

    answer.refresh_from_db(fields=["answer", "answer_file"])
    assert answer.answer == "file://" + stored_name
    assert answer.answer_file.name == stored_name


def test_save_answer_file_strips_exif_from_raster_image(
    django_capture_on_commit_callbacks,
):
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Snoopcam"
    buf = BytesIO()
    Image.new("RGB", (20, 20), color="red").save(buf, format="JPEG", exif=exif)
    upload = SimpleUploadedFile("photo.JPG", buf.getvalue(), content_type="image/jpeg")

    with scope(event=question.event), django_capture_on_commit_callbacks(execute=True):
        answer = save_answer(question=question, value=upload, target_object=submission)
    answer.refresh_from_db(fields=["answer", "answer_file"])

    assert answer.answer_file.name.endswith(".webp")
    assert answer.answer == "file://" + answer.answer_file.name
    with Image.open(answer.answer_file.path) as result:
        assert "exif" not in result.info
        assert not result.getexif()


def test_save_answer_file_keeps_undecodable_image(django_capture_on_commit_callbacks):
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    upload = SimpleUploadedFile("photo.png", b"not a png", content_type="image/png")

    with (
        scope(event=question.event),
        django_capture_on_commit_callbacks(execute=True) as callbacks,
    ):
        answer = save_answer(question=question, value=upload, target_object=submission)
    stored_name = answer.answer_file.name
    answer.refresh_from_db(fields=["answer", "answer_file"])

    assert len(callbacks) == 1

    assert answer.answer_file.name == stored_name
    assert answer.answer == "file://" + stored_name
    with answer.answer_file.open("rb") as fp:
        assert fp.read() == b"not a png"


def test_save_answer_file_queued_processing_skips_replaced_file(
    make_image, django_capture_on_commit_callbacks
):
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    with (
        scope(event=question.event),
        patch("pretalx.common.models.mixins.task_process_image.apply_async") as queue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        answer = save_answer(
            question=question, value=make_image("first.png"), target_object=submission
        )
        second = make_image("second.png", width=2, height=2)
        second_bytes = second.read()
        second.seek(0)
        answer = save_answer(
            question=question, value=second, target_object=submission, existing=answer
        )
    second_name = answer.answer_file.name

    task_process_image(**queue.call_args_list[0].kwargs["kwargs"])

    answer.refresh_from_db(fields=["answer", "answer_file"])
    assert answer.answer_file.name == second_name
    with answer.answer_file.open("rb") as fp:
        assert fp.read() == second_bytes


def test_save_answer_file_resave_does_not_reprocess(
    make_image, django_capture_on_commit_callbacks
):
    question = QuestionFactory(variant=QuestionVariant.FILE)
    submission = SubmissionFactory(event=question.event)
    with scope(event=question.event), django_capture_on_commit_callbacks(execute=True):
        answer = save_answer(
            question=question, value=make_image("photo.png"), target_object=submission
        )
    answer.refresh_from_db(fields=["answer", "answer_file"])
    with default_storage.open(answer.answer_file.name, "rb") as fp:
        processed_bytes = fp.read()

    with (
        scope(event=question.event),
        patch(
            "pretalx.common.models.mixins.task_process_image.apply_async",
            wraps=task_process_image.apply_async,
        ) as queue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        answer = save_answer(
            question=question,
            value=answer.answer_file,
            target_object=submission,
            existing=answer,
        )

    assert not queue.called
    answer.refresh_from_db(fields=["answer", "answer_file"])
    with answer.answer_file.open("rb") as fp:
        assert fp.read() == processed_bytes


def _zip_entries(cached_file):
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_export_answer_files_bundles_file_answers():
    event = EventFactory()
    string_question = QuestionFactory(event=event, variant=QuestionVariant.STRING)
    question = QuestionFactory(event=event, variant=QuestionVariant.FILE)
    unused = CachedFileFactory()
    empty = CachedFileFactory()
    cached_file = CachedFileFactory()

    assert export_answer_files(question=string_question, cached_file=unused) is None
    unused.refresh_from_db()
    assert not unused.file

    with scope(event=event):
        assert export_answer_files(question=question, cached_file=empty) == str(
            empty.id
        )
        assert _zip_entries(empty) == {}

        a1 = AnswerFactory(
            submission=SubmissionFactory(event=event), question=question, answer="doc"
        )
        a1.answer_file.save("doc.pdf", ContentFile(b"content 1"))
        a2 = AnswerFactory(
            submission=SubmissionFactory(event=event), question=question, answer="doc"
        )
        a2.answer_file.save("doc.pdf", ContentFile(b"content 2"))
        AnswerFactory(
            submission=SubmissionFactory(event=event),
            question=question,
            answer="placeholder",
            answer_file="",
        )

        result = export_answer_files(question=question, cached_file=cached_file)

    assert result == str(cached_file.id)
    entries = _zip_entries(cached_file)
    assert len(entries) == 2
    assert set(entries.values()) == {b"content 1", b"content 2"}


def test_export_answer_files_deduplicates_filenames():
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
    entries = _zip_entries(cached_file)
    assert set(entries) == {"doc.pdf", "doc_1.pdf"}
    assert set(entries.values()) == {b"file 1", b"file 2"}


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
    assert list(_zip_entries(cached_file).values()) == [b""]


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


def test_replace_question_options_replaces_then_clears():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question, answer="Old A")
    AnswerOptionFactory(question=question, answer="Old B")

    replace_question_options(
        question=question, options_data=[{"answer": "New A"}, {"answer": "New B"}]
    )

    options = sorted(str(a) for a in question.options.values_list("answer", flat=True))
    assert options == ["New A", "New B"]

    replace_question_options(question=question, options_data=[])

    assert question.options.count() == 0


def test_delete_question_cascades_draft_answers_options_and_logs():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    speaker_question = QuestionFactory(
        event=event, variant=QuestionVariant.STRING, target=QuestionTarget.SPEAKER
    )
    with scope(event=event):
        question.log_action(".create", orga=True)
        assert question.logged_actions().count() == 1
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft_answer = AnswerFactory(question=question, submission=draft, answer="x")
        speaker = SpeakerFactory(event=event)
        draft.speakers.add(speaker)
        speaker_answer = AnswerFactory(
            question=speaker_question, submission=None, speaker=speaker, answer="x"
        )

        delete_question(question)
        delete_question(speaker_question)

        assert not Question.all_objects.filter(
            pk__in=[question.pk, speaker_question.pk]
        ).exists()
        assert not AnswerOption.objects.filter(question_id=question.pk).exists()
        assert not Answer.objects.filter(
            pk__in=[draft_answer.pk, speaker_answer.pk]
        ).exists()


def test_delete_question_protects_live_answers_and_keeps_draft_answers():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.STRING)
    with scope(event=event):
        draft_answer = AnswerFactory(
            question=question,
            submission=SubmissionFactory(event=event, state=SubmissionStates.DRAFT),
            answer="draft",
        )
        live_answer = AnswerFactory(
            question=question, submission=SubmissionFactory(event=event), answer="live"
        )

    with scope(event=event), pytest.raises(ProtectedError):
        delete_question(question)

    with scope(event=event):
        assert Question.all_objects.filter(pk=question.pk).exists()
        assert set(Answer.objects.filter(question=question)) == {
            draft_answer,
            live_answer,
        }


def test_delete_question_protects_answers_of_non_draft_only_speakers():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.STRING, target=QuestionTarget.SPEAKER
    )
    with scope(event=event):
        withdrawn_speaker = SpeakerFactory(event=event)
        SubmissionFactory(event=event, state=SubmissionStates.DRAFT).speakers.add(
            withdrawn_speaker
        )
        SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN).speakers.add(
            withdrawn_speaker
        )
        answers = {
            AnswerFactory(
                question=question,
                submission=None,
                speaker=withdrawn_speaker,
                answer="x",
            ),
            AnswerFactory(
                question=question,
                submission=None,
                speaker=SpeakerFactory(event=event),
                answer="x",
            ),
        }

    with scope(event=event), pytest.raises(ProtectedError):
        delete_question(question)

    with scope(event=event):
        assert Question.all_objects.filter(pk=question.pk).exists()
        assert set(Answer.objects.filter(question=question)) == answers


def test_delete_question_never_cascades_for_reviewer_target():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.STRING, target=QuestionTarget.REVIEWER
    )
    with scope(event=event):
        leftover = AnswerFactory(
            question=question,
            submission=SubmissionFactory(event=event, state=SubmissionStates.DRAFT),
            answer="leftover",
        )

    with scope(event=event), pytest.raises(ProtectedError):
        delete_question(question)

    with scope(event=event):
        assert Question.all_objects.filter(pk=question.pk).exists()
        assert list(Answer.objects.filter(question=question)) == [leftover]


def _option_order(question):
    return list(question.options.order_by("position").values_list("answer", flat=True))


def test_apply_uploaded_options_replace_and_merge():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        apply_uploaded_options(question=question, options=None, replace=True)
        assert question.options.count() == 0

        old = AnswerOptionFactory(question=question, answer="Old", position=5)
        AnswerFactory(question=question, answer="Old")

        apply_uploaded_options(
            question=question, options=["New A", "New B"], replace=True
        )

        assert _option_order(question) == ["New A", "New B"]
        assert question.answers.count() == 0
        assert not question.options.filter(pk=old.pk).exists()
        new_a = question.options.get(answer="New A")

        apply_uploaded_options(
            question=question, options=["New B", "New A", "C"], replace=False
        )

        assert _option_order(question) == ["New B", "New A", "C"]
        assert question.options.get(pk=new_a.pk).position == 2

        apply_uploaded_options(
            question=question, options=["New B", "New A", "C"], replace=False
        )

        assert _option_order(question) == ["New B", "New A", "C"]
        assert question.options.count() == 3


def test_apply_uploaded_options_merge_i18n_on_multilingual_event():
    event = EventFactory(locales=["en", "de"], content_locales=["en", "de"])
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    with scope(event=event):
        AnswerOptionFactory(question=question, answer="Existing", position=1)

        options = [
            LazyI18nString({"en": "Existing", "de": "Bestehend"}),
            LazyI18nString({"en": "New", "de": "Neu"}),
        ]
        apply_uploaded_options(question=question, options=options, replace=False)

        assert question.options.count() == 2


def test_set_question_active_toggles_and_logs_changes_only():
    event = EventFactory()
    user = UserFactory()
    question = QuestionFactory(event=event, active=False)

    with scope(event=event):
        set_question_active(question, active=True, person=user)

        question.refresh_from_db(fields=["active"])
        assert question.active is True
        log = question.logged_actions().get()
        assert log.action_type == "pretalx.question.activate"
        assert log.person == user

        set_question_active(question, active=True)
        assert question.logged_actions().count() == 1

        set_question_active(question, active=False, person=user)

        question.refresh_from_db(fields=["active"])
        assert question.active is False
        assert [
            log.action_type for log in question.logged_actions().order_by("pk")
        ] == ["pretalx.question.activate", "pretalx.question.deactivate"]


def test_reorder_questions_updates_positions_and_logs_only_changes():
    event = EventFactory()
    user = UserFactory()
    with scope(event=event):
        q1 = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=0)
        q2 = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION, position=1)
        logs = event.logged_actions().filter(action_type="pretalx.question.reorder")

        reorder_questions(
            event,
            target=QuestionTarget.SUBMISSION,
            ordered_positions=[(0, q1.pk), (1, q2.pk)],
            person=user,
        )

        assert not logs.exists()

        reorder_questions(
            event,
            target=QuestionTarget.SUBMISSION,
            ordered_positions=[(0, 999999), (0, q2.pk), (1, q1.pk)],
            person=user,
        )

        q1.refresh_from_db(fields=["position"])
        q2.refresh_from_db(fields=["position"])
        assert (q1.position, q2.position) == (1, 0)
        assert logs.count() == 1
