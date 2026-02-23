import datetime as dt
import logging

from django.dispatch import receiver
from django.utils.timezone import now

from pretalx.common.signals import minimum_interval, periodic_task

logger = logging.getLogger(__name__)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=15)
def mark_stale_sending_mails_as_failed(sender, **kwargs):
    from pretalx.mail.models import QueuedMail, QueuedMailStates  # noqa: PLC0415

    cutoff = now() - dt.timedelta(hours=1)
    count = QueuedMail.objects.filter(
        state=QueuedMailStates.SENDING,
        updated__lt=cutoff,
    ).update(
        state=QueuedMailStates.DRAFT,
        error_data={
            "error": "Timed out waiting for delivery confirmation",
            "type": "TimeoutError",
        },
        error_timestamp=now(),
        updated=now(),
    )
    if count:
        logger.warning("Marked %d stale sending mails as failed", count)
