# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

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
        data = []
        submissions = Submission.objects.filter(
            event=self.event,
            state__in=[SubmissionStates.ACCEPTED, SubmissionStates.CONFIRMED],
        )
        for speaker in self.event.submitters:
            speaker_subs = submissions.filter(speakers=speaker)
            accepted_talks = speaker_subs.filter(
                state=SubmissionStates.ACCEPTED
            ).exists()
            confirmed_talks = speaker_subs.filter(
                state=SubmissionStates.CONFIRMED
            ).exists()
            if not accepted_talks and not confirmed_talks:
                continue
            data.append(
                {
                    "name": speaker.get_display_name(),
                    "email": speaker.user.email,
                    "confirmed": str(bool(confirmed_talks)),
                }
            )
        return fieldnames, data
