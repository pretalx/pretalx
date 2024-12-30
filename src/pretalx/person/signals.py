from django.dispatch import Signal, receiver

from pretalx.common.signals import register_data_exporters


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_csv_speaker")
def register_speaker_csv_exporter(sender, **kwargs):
    from pretalx.person.exporters import CSVSpeakerExporter

    return CSVSpeakerExporter


deactivate_user = Signal()
"""
This signal is sent out when a user is deactivated (i.e. deleted on the
frontend).

You will get the user as a keyword argument ``user``. Receivers are expected to
delete any personal information they might have stored about this user.
"""
