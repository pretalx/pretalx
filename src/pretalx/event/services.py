# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.common.models.file import CachedFile
from pretalx.common.signals import periodic_task
from pretalx.event.models import Event


@app.task(name="pretalx.event.periodic_event_services")
def task_periodic_event_services(event_slug):
    with scopes_disabled():
        event = (
            Event.objects.filter(slug=event_slug)
            .select_related("cfp")
            .prefetch_related(
                "_settings_objects",
                "submissions__slots",
                "schedules",
                "review_phases",
                "score_categories",
            )
            .first()
        )
    if not event:
        return

    _now = now()
    with scope(event=event):
        if (
            not event.settings.sent_mail_cfp_closed
            and event.cfp.deadline
            and dt.timedelta(0) <= (_now - event.cfp.deadline) <= dt.timedelta(days=1)
        ):
            event.send_orga_mail(event.settings.mail_text_cfp_closed)
            event.settings.sent_mail_cfp_closed = True

        if (
            not event.settings.sent_mail_event_over
            and (
                (_now.date() - dt.timedelta(days=3))
                <= event.date_to
                <= (_now.date() - dt.timedelta(days=1))
            )
            and event.current_schedule
            and event.current_schedule.talks.filter(is_visible=True).count()
        ):
            event.send_orga_mail(event.settings.mail_text_event_over, stats=True)
            event.settings.sent_mail_event_over = True


@receiver(periodic_task)
def periodic_event_services(sender, **kwargs):
    cutoff = now() - dt.timedelta(days=3)
    for event in Event.objects.filter(date_to__gte=cutoff.date()):
        with scope(event=event):
            task_periodic_event_services.apply_async(
                args=(event.slug,), ignore_result=True
            )
            event.update_review_phase()


@receiver(signal=periodic_task)
def clean_cached_files(sender, **kwargs):
    for cf in CachedFile.objects.filter(expires__lt=now()):
        cf.delete()
