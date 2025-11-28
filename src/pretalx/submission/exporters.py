# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretalx.common.exporter import BaseExporter, CSVExporterMixin
from pretalx.common.signals import register_data_exporters
from pretalx.submission.models import Answer
from pretalx.submission.rules import filter_answers_by_team_access


class SpeakerQuestionData(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-question-circle"
    cors = "*"
    group = "speaker"
    filename_identifier = "speaker-questions"

    @property
    def verbose_name(self):
        return _("Custom fields data") + " (" + _("speakers") + ")"

    def get_csv_data(self, request, **kwargs):
        field_names = ["code", "name", "email", "question", "answer"]
        data = []
        qs = (
            Answer.objects.filter(
                question__target="speaker",
                question__event=self.event,
                question__active=True,
                person__isnull=False,
            )
            .select_related("question", "person")
            .order_by("person__name")
        )
        qs = filter_answers_by_team_access(qs, request.user)
        for answer in qs:
            data.append(
                {
                    "code": answer.person.code,
                    "name": answer.person.name,
                    "email": answer.person.email,
                    "question": answer.question.question,
                    "answer": answer.answer_string,
                }
            )
        return field_names, data


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_speaker_question")
def register_speaker_question_exporter(sender, **kwargs):
    return SpeakerQuestionData


class SubmissionQuestionData(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-question-circle-o"
    cors = "*"
    filename_identifier = "submission-questions"

    @property
    def verbose_name(self):
        return _("Custom fields data") + " (" + _("submissions") + ")"

    def get_csv_data(self, request, **kwargs):
        field_names = ["code", "title", "question", "answer"]
        data = []
        qs = Answer.objects.filter(
            question__target="submission",
            question__event=self.event,
            question__active=True,
        ).order_by("submission__title")
        qs = filter_answers_by_team_access(qs, request.user)
        for answer in qs:
            data.append(
                {
                    "code": answer.submission.code,
                    "title": answer.submission.title,
                    "question": answer.question.question,
                    "answer": answer.answer_string,
                }
            )
        return field_names, data


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_submission_question")
def register_submission_question_exporter(sender, **kwargs):
    return SubmissionQuestionData
