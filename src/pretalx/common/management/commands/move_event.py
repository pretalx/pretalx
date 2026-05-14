# SPDX-FileCopyrightText: 2021-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scope

from pretalx.event.domain.event import move_full_event
from pretalx.event.models import Event


class Command(BaseCommand):
    help = "Move an event to a given date (default: today)"

    def add_arguments(self, parser):
        parser.add_argument("--event", type=str, help="Slug of the event to be used.")
        parser.add_argument(
            "--date", type=str, help="Date in the format YYYY-MM-DD. Default: today"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        event_slug = options.get("event")
        start_date = options.get("date")

        start_date = dt.date.fromisoformat(start_date) if start_date else now().date()

        event = Event.objects.get(slug=event_slug)

        with scope(event=event):
            move_full_event(event, start_date)
