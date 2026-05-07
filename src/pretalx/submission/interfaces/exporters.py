# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.common.exporter import BaseExporter, CSVExporterMixin
from pretalx.submission.domain.queries.question import answers_for_user
from pretalx.submission.models import QuestionTarget


class SpeakerQuestionData(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-question-circle"
    cors = "*"
    group = "speaker"
    filename_identifier = "speaker-questions"

    @property
    def verbose_name(self):
        return _("Custom fields data") + " (" + _("Speakers") + ")"

    def get_csv_data(self, request, **kwargs):
        field_names = ["code", "name", "email", "question", "answer"]
        qs = (
            answers_for_user(self.event, request.user)
            .filter(
                question__target=QuestionTarget.SPEAKER,
                question__active=True,
                speaker__isnull=False,
            )
            .select_related("speaker__user")
            .order_by("speaker__name")
        )
        data = [
            {
                "code": answer.speaker.code,
                "name": answer.speaker.get_display_name(),
                "email": answer.speaker.user.email,
                "question": answer.question.question,
                "answer": answer.answer_string,
            }
            for answer in qs
        ]
        return field_names, data


class SubmissionQuestionData(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-question-circle-o"
    cors = "*"
    filename_identifier = "submission-questions"

    @property
    def verbose_name(self):
        return _("Custom fields data") + " (" + _("Submissions") + ")"

    def get_csv_data(self, request, **kwargs):
        field_names = ["code", "title", "question", "answer"]
        qs = (
            answers_for_user(self.event, request.user)
            .filter(question__target=QuestionTarget.SUBMISSION, question__active=True)
            .order_by("submission__title")
        )
        data = [
            {
                "code": answer.submission.code,
                "title": answer.submission.title,
                "question": answer.question.question,
                "answer": answer.answer_string,
            }
            for answer in qs
        ]
        return field_names, data
