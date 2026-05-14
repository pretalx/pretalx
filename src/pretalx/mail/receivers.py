# SPDX-FileCopyrightText: 2021-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from django.dispatch import receiver

from pretalx.common.signals import minimum_interval, periodic_task

logger = logging.getLogger(__name__)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=15)
def expire_stale_mails_periodic(sender, **kwargs):
    from pretalx.mail.domain.queue import (  # noqa: PLC0415 -- receiver
        expire_stale_queued_mails,
    )

    count = expire_stale_queued_mails()
    if count:
        logger.warning("Expired %d stale queued mails", count)
