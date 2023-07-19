# SPDX-FileCopyrightText: 2023 pretalx contributors <https://github.com/pretalx/pretalx/graphs/contributors>
#
# SPDX-License-Identifier: Apache-2.0

from django.apps import AppConfig


class ScheduleConfig(AppConfig):
    name = "pretalx.schedule"

    def ready(self):
        from . import signals  # noqa
