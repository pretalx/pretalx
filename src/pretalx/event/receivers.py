# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.signals import minimum_interval, periodic_task


@receiver(periodic_task)
def periodic_event_services(sender, **kwargs):
    from pretalx.event.domain.lifecycle import (  # noqa: PLC0415 -- receiver
        events_pending_lifecycle_notifications,
    )
    from pretalx.event.models import Event  # noqa: PLC0415 -- receiver
    from pretalx.event.tasks import (  # noqa: PLC0415 -- receiver
        task_periodic_event_services,
    )
    from pretalx.submission.domain.review import (  # noqa: PLC0415 -- receiver
        update_review_phase,
    )

    cutoff = now() - dt.timedelta(days=3)
    events = Event.objects.filter(date_to__gte=cutoff.date())
    for slug in events_pending_lifecycle_notifications(events).values_list(
        "slug", flat=True
    ):
        task_periodic_event_services.apply_async(args=(slug,), ignore_result=True)
    for event in events:
        with scope(event=event):
            update_review_phase(event)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=15)
def clean_cached_files(sender, **kwargs):
    from pretalx.common.models.file import CachedFile  # noqa: PLC0415 -- receiver

    for cf in CachedFile.objects.filter(expires__lt=now()):
        cf.delete()
