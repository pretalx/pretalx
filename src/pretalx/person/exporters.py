from django.utils.translation import gettext_lazy as _

from pretalx.common.exporter import BaseExporter, CSVExporterMixin
from pretalx.submission.models import SubmissionStates


class CSVSpeakerExporter(CSVExporterMixin, BaseExporter):
    public = False
    icon = "fa-users"
    identifier = "speakers.csv"
    cors = "*"
    group = "speaker"

    @property
    def verbose_name(self):
        return _("Speaker CSV")

    @property
    def filename(self):
        base_filename = f"{self.event.slug}-speakers.csv"
        return self.get_timestamp_filename(base_filename)

    def get_data(self, **kwargs):
        fieldnames = ["name", "email", "confirmed"]
        data = []
        for speaker in self.event.submitters:
            accepted_talks = speaker.submissions.filter(
                event=self.event, state=SubmissionStates.ACCEPTED
            ).exists()
            confirmed_talks = speaker.submissions.filter(
                event=self.event, state=SubmissionStates.CONFIRMED
            ).exists()
            if not accepted_talks and not confirmed_talks:
                continue
            data.append(
                {
                    "name": speaker.get_display_name(),
                    "email": speaker.email,
                    "confirmed": str(bool(confirmed_talks)),
                }
            )
        return fieldnames, data
