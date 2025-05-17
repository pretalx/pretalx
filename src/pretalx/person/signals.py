from django.dispatch import Signal, receiver

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


speaker_forms = EventPluginSignal()
"""
This signal is sent out to inject additional form fields on the submission
pages in the internal organiser area.

As with all plugin signals, the ``sender`` keyword argument will contain the
event. Additionally, the signal will be called with the ``request`` it is
processing, and the ``person`` which is currently displayed.
The receivers are expected to return one or more forms.
"""


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_csv_speaker")
def register_speaker_csv_exporter(sender, **kwargs):
    from pretalx.person.exporters import CSVSpeakerExporter

    return CSVSpeakerExporter


delete_user = Signal()
"""
This signal is sent out when a user is deleted - both when deleted on the
frontend ("deactivated") and actually removed ("shredded").

You will get the user as a keyword argument ``user``. Receivers are expected to
delete any personal information they might have stored about this user.

Additionally, you will get the keyword argument ``db_delete`` when the user
object will be deleted from the database. If you have any foreign keys to the
user object, you should delete them here.
"""
