# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.management.base import BaseCommand

from pretalx.common.signals import periodic_task


class Command(BaseCommand):
    help = "Run periodic tasks"

    def handle(self, *args, **options):
        periodic_task.send_robust(self)
