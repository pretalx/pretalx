# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.dispatch import Signal, receiver
from django.utils.timezone import now

from pretalx.common.signals import (
    minimum_interval,
    periodic_task,
    register_data_exporters,
)
from pretalx.person.models import ProfilePicture, UserApiToken

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


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_csv_speaker")
def register_speaker_csv_exporter(sender, **kwargs):
    from pretalx.person.interfaces.exporters import (  # noqa: PLC0415 -- avoid circular import
        CSVSpeakerExporter,
    )

    return CSVSpeakerExporter


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60)
def run_update_check(sender, **kwargs):
    UserApiToken.objects.filter(expires__lt=now()).delete()


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60 * 24)
def clean_orphaned_profile_pictures(sender, **kwargs):
    cutoff = now() - dt.timedelta(days=30)
    pictures = ProfilePicture.objects.filter(
        users__isnull=True, speakers__isnull=True, updated__lt=cutoff
    )
    for picture in pictures:
        # Object-level delete to trigger file cleanup
        picture.delete()
