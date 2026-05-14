# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver

from pretalx.common.signals import register_data_exporters


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_speaker_question")
def register_speaker_question_exporter(sender, **kwargs):
    from pretalx.submission.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        SpeakerQuestionData,
    )

    return SpeakerQuestionData


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_submission_question")
def register_submission_question_exporter(sender, **kwargs):
    from pretalx.submission.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        SubmissionQuestionData,
    )

    return SubmissionQuestionData
