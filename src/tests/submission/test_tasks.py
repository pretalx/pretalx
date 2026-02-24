from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core import mail as djmail
from django.core.files.base import ContentFile
from django_scopes import scope, scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.models import QueuedMail
from pretalx.submission.models.question import Answer
from pretalx.submission.models.review import Review
from pretalx.submission.tasks import (
    export_question_files,
    recalculate_all_review_scores,
    task_send_initial_mails,
)
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_recalculate_all_review_scores_updates_stale_score(event):
    """Stale review scores are recalculated from the scores M2M."""
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission)
    # Bypass save() to set a stale score that doesn't match the empty M2M
    with scopes_disabled():
        Review.objects.filter(pk=review.pk).update(score=42)

    recalculate_all_review_scores(event_id=event.pk)

    review.refresh_from_db()
    assert review.score is None  # No M2M scores → recalculated to None


@pytest.mark.django_db
def test_recalculate_all_review_scores_missing_event():
    result = recalculate_all_review_scores(event_id=99999)
    assert result is None


@pytest.mark.django_db
def test_export_question_files_missing_question():
    cached_file = CachedFileFactory()
    result = export_question_files(
        question_id=99999, cached_file_id=str(cached_file.id)
    )
    assert result is None
    cached_file.refresh_from_db()
    assert not cached_file.file


@pytest.mark.django_db
def test_export_question_files_missing_cached_file():
    question = QuestionFactory()
    result = export_question_files(
        question_id=question.pk, cached_file_id="00000000-0000-0000-0000-000000000000"
    )
    assert result is None


@pytest.mark.django_db
def test_export_question_files_non_file_question():
    question = QuestionFactory(variant="string")
    cached_file = CachedFileFactory()

    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )

    assert result is None
    cached_file.refresh_from_db()
    assert not cached_file.file


@pytest.mark.django_db
def test_export_question_files_no_answers():
    question = QuestionFactory(variant="file")
    cached_file = CachedFileFactory()

    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        assert zf.namelist() == []


@pytest.mark.django_db
def test_export_question_files_creates_zip():
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        answer = Answer.objects.create(
            submission=submission, question=question, answer="doc.pdf"
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"pdf content"))
        answer.save()

    cached_file = CachedFileFactory()
    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b"pdf content"


@pytest.mark.django_db
def test_export_question_files_multiple_answers():
    """Multiple answers each produce a file in the zip."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = Answer.objects.create(
            submission=submission1, question=question, answer="doc.pdf"
        )
        a1.answer_file.save("doc.pdf", ContentFile(b"content 1"))
        a1.save()
        a2 = Answer.objects.create(
            submission=submission2, question=question, answer="doc.pdf"
        )
        a2.answer_file.save("doc.pdf", ContentFile(b"content 2"))
        a2.save()

    cached_file = CachedFileFactory()
    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        contents = {zf.read(n) for n in names}
        assert contents == {b"content 1", b"content 2"}


@pytest.mark.django_db
def test_export_question_files_deduplicates_filenames():
    """When safe_filename produces identical basenames, counter suffixes are added."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = Answer.objects.create(submission=s1, question=question, answer="doc.pdf")
        a1.answer_file.save("doc.pdf", ContentFile(b"file 1"))
        a1.save()
        a2 = Answer.objects.create(submission=s2, question=question, answer="doc.pdf")
        a2.answer_file.save("doc.pdf", ContentFile(b"file 2"))
        a2.save()

    cached_file = CachedFileFactory()
    with patch("pretalx.submission.tasks.safe_filename", return_value="doc.pdf"):
        result = export_question_files(
            question_id=question.pk, cached_file_id=str(cached_file.id)
        )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = sorted(zf.namelist())
        assert names == ["doc.pdf", "doc_1.pdf"]


@pytest.mark.django_db
def test_task_send_initial_mails():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        submission.speakers.add(speaker)

    djmail.outbox = []
    with scopes_disabled():
        mail_count = QueuedMail.objects.count()

    task_send_initial_mails(submission_id=submission.pk, person_id=user.pk)

    with scopes_disabled():
        assert QueuedMail.objects.count() == mail_count + 1
        mail = QueuedMail.objects.order_by("-pk").first()
        assert list(mail.to_users.all()) == [user]
        assert submission.title in mail.subject
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert submission.title in djmail.outbox[0].subject


@pytest.mark.django_db
def test_task_send_initial_mails_missing_submission():
    user = UserFactory()
    djmail.outbox = []
    with scopes_disabled():
        mail_count = QueuedMail.objects.count()

    task_send_initial_mails(submission_id=99999, person_id=user.pk)

    with scopes_disabled():
        assert QueuedMail.objects.count() == mail_count
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_task_send_initial_mails_missing_user():
    submission = SubmissionFactory()
    djmail.outbox = []
    with scopes_disabled():
        mail_count = QueuedMail.objects.count()

    task_send_initial_mails(submission_id=submission.pk, person_id=99999)

    with scopes_disabled():
        assert QueuedMail.objects.count() == mail_count
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_task_send_initial_mails_handles_send_mail_exception():
    """SendMailException during send_initial_mails is caught and logged."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    with scopes_disabled():
        submission.speakers.add(speaker)

    djmail.outbox = []
    with patch.object(
        type(submission),
        "send_initial_mails",
        side_effect=SendMailException("SMTP error"),
    ):
        task_send_initial_mails(submission_id=submission.pk, person_id=user.pk)

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_export_question_files_skips_empty_answer_file():
    """Answers where answer_file is falsy are skipped."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        Answer.objects.create(
            submission=submission,
            question=question,
            answer="placeholder",
            answer_file="",
        )

    cached_file = CachedFileFactory()
    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        assert zf.namelist() == []


@pytest.mark.django_db
def test_export_question_files_handles_unreadable_file():
    """OSError when reading a file is caught and logged."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        answer = Answer.objects.create(
            submission=submission, question=question, answer="doc.pdf"
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"content"))
        answer.save()

    cached_file = CachedFileFactory()
    with patch(
        "pretalx.submission.tasks.shutil.copyfileobj",
        side_effect=OSError("Permission denied"),
    ):
        result = export_question_files(
            question_id=question.pk, cached_file_id=str(cached_file.id)
        )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b""


@pytest.mark.django_db
def test_export_question_files_general_exception():
    """General exception during zip creation is caught and returns None."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant="file")
    s1 = SubmissionFactory(event=event)

    with scope(event=event):
        a1 = Answer.objects.create(submission=s1, question=question, answer="doc.pdf")
        a1.answer_file.save("doc.pdf", ContentFile(b"content"))
        a1.save()

    cached_file = CachedFileFactory()
    with patch(
        "pretalx.submission.tasks.zipfile.ZipFile",
        side_effect=RuntimeError("disk full"),
    ):
        result = export_question_files(
            question_id=question.pk, cached_file_id=str(cached_file.id)
        )

    assert result is None
