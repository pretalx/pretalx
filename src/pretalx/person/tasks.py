# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: fkusei

import logging

from django.dispatch import receiver
from django.utils.timezone import now

from pretalx.common.signals import minimum_interval, periodic_task
from pretalx.person.models import UserApiToken

logger = logging.getLogger(__name__)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60)
def run_update_check(sender, **kwargs):
    UserApiToken.objects.filter(expires__lt=now()).delete()
