# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from io import BytesIO
from zipfile import ZipFile

import pytest
from django.core.files.base import ContentFile
from django_scopes import scope

from pretalx.common.models.file import CachedFile
from pretalx.submission.models.question import Answer
from pretalx.submission.tasks import export_question_files


@pytest.mark.django_db
def test_export_question_files_missing_question():
    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    result = export_question_files(
        question_id=99999, cached_file_id=str(cached_file.id)
    )
    assert result is None
    cached_file.refresh_from_db()
    assert not cached_file.file


@pytest.mark.django_db
def test_export_question_files_missing_cached_file(question):
    result = export_question_files(
        question_id=question.pk, cached_file_id="00000000-0000-0000-0000-000000000000"
    )
    assert result is None


@pytest.mark.django_db
def test_export_question_files_non_file_question(question):
    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    assert question.variant != "file"
    result = export_question_files(
        question_id=question.pk, cached_file_id=str(cached_file.id)
    )
    assert result is None
    cached_file.refresh_from_db()
    assert not cached_file.file


@pytest.mark.django_db
def test_export_question_files_no_answers(event, file_question):
    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    result = export_question_files(
        question_id=file_question.pk, cached_file_id=str(cached_file.id)
    )
    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        assert zf.namelist() == []


@pytest.mark.django_db
def test_export_question_files_creates_zip(event, file_question, submission, speaker):
    with scope(event=event):
        answer = Answer.objects.create(
            submission=submission,
            question=file_question,
            person=speaker,
            answer="doc.pdf",
        )
        answer.answer_file.save("doc.pdf", ContentFile(b"pdf content"))
        answer.save()

    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    result = export_question_files(
        question_id=file_question.pk, cached_file_id=str(cached_file.id)
    )
    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert zf.read(names[0]) == b"pdf content"


@pytest.mark.django_db
def test_export_question_files_speaker_target(event, speaker_file_question, speaker):
    with scope(event=event):
        answer = Answer.objects.create(
            question=speaker_file_question,
            person=speaker,
            answer="cv.pdf",
        )
        answer.answer_file.save("cv.pdf", ContentFile(b"CV content"))
        answer.save()

    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    result = export_question_files(
        question_id=speaker_file_question.pk, cached_file_id=str(cached_file.id)
    )
    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    with ZipFile(BytesIO(cached_file.file.read()), "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert speaker.code in names[0]
