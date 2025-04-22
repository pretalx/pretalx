from django.dispatch import receiver

from pretalx.common.signals import EventPluginSignal, register_data_exporters

speaker_form_html = EventPluginSignal()
"""
This signal is sent out to display additional information on the speaker
pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``person`` which is currently displayed.
The receivers are expected to return HTML.
"""


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_csv_speaker")
def register_speaker_csv_exporter(sender, **kwargs):
    from pretalx.person.exporters import CSVSpeakerExporter

    return CSVSpeakerExporter
