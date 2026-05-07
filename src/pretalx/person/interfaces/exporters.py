# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Exists, OuterRef, Q
from django.utils.translation import gettext_lazy as _

from pretalx.common.exporter import BaseExporter, CSVExporterMixin
from pretalx.submission.models import Submission, SubmissionStates


class CSVSpeakerExporter(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-users"
    identifier = "speakers.csv"
    cors = "*"
    group = "speaker"
    filename_identifier = "speakers"

    @property
    def verbose_name(self):
        return _("Speaker CSV")

    def get_csv_data(self, request, **kwargs):
        fieldnames = ["name", "email", "confirmed"]
        speaker_subs = Submission.objects.filter(speakers=OuterRef("pk"))
        speakers = self.event.submitters.annotate(
            has_accepted=Exists(speaker_subs.filter(state=SubmissionStates.ACCEPTED)),
            has_confirmed=Exists(speaker_subs.filter(state=SubmissionStates.CONFIRMED)),
        ).filter(Q(has_accepted=True) | Q(has_confirmed=True))
        data = [
            {
                "name": speaker.get_display_name(),
                "email": speaker.user.email,
                "confirmed": str(speaker.has_confirmed),
            }
            for speaker in speakers
        ]
        return fieldnames, data
