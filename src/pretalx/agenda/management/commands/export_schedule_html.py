# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import logging

from django.core.management.base import BaseCommand, CommandError
from django_scopes import scopes_disabled

from pretalx.agenda.html_export import export_event_html
from pretalx.event.models import Event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("event", type=str)
        parser.add_argument("--zip", action="store_true")

    def handle(self, *args, **options):
        event_slug = options["event"]
        with scopes_disabled():
            try:
                event = Event.objects.get(slug__iexact=event_slug)
            except Event.DoesNotExist:
                raise CommandError(
                    f'Could not find event with slug "{event_slug}".'
                ) from None

        logger.info("Exporting %s", event.name)
        try:
            destination = export_event_html(event, as_zip=options["zip"])
        except Exception as exc:
            logger.exception("Export failed")
            raise CommandError(f"Export failed: {exc}") from exc
        logger.info("Exported to %s", destination)
