# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: fkusei

import datetime as dt
import logging

from django.dispatch import receiver
from django.utils.timezone import now

from pretalx.common.signals import minimum_interval, periodic_task
from pretalx.person.models import UserApiToken
from pretalx.person.models import ProfilePicture

logger = logging.getLogger(__name__)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60)
def run_update_check(sender, **kwargs):
    UserApiToken.objects.filter(expires__lt=now()).delete()


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60 * 24)
def clean_orphaned_profile_pictures(sender, **kwargs):

    cutoff = now() - dt.timedelta(days=30)
    pictures = ProfilePicture.objects.filter(
        users__isnull=True,
        speakers__isnull=True,
        updated__lt=cutoff,
    )
    for picture in pictures:
        # Object-level delete to trigger file cleanup
        picture.delete()
